import threading
import unittest
from unittest.mock import patch, Mock
from rts_controller.paused import PausedSession
from rts_controller.ra2 import BridgeError
from rts_controller.paused_move import move
from test_ra2 import game


class FakeSession(PausedSession):
    def __init__(self):
        super().__init__(armed=True)
        self.frame = 10
        self.calls = []
        self.increment = 1
        self.single_step = True

    def request(self, name, fields=None):
        self.calls.append(name)
        if name == "InspectConfiguration": return {"config": {"singleStep": self.single_step}}
        if name == "GetGameState":
            before = self.frame
            self.frame += self.increment
            return {"state": {"currentFrame": before}}
        state = game(self.frame)
        state["houses"][0]["isHumanPlayer"] = True
        return {"data": {"gameState": state}}


class PausedTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("rts_controller.paused.time.sleep")
        patcher.start(); self.addCleanup(patcher.stop)

    def test_requires_arming(self):
        with self.assertRaises(ValueError): PausedSession()

    def test_observation_does_not_advance(self):
        s = FakeSession()
        self.assertEqual(s.stable()["frame"], 10)
        self.assertNotIn("GetGameState", s.calls)

    def test_initial_types_read_only_once(self):
        s = FakeSession()
        s.observe(); first = s.calls.count("ReadValue")
        s.observe()
        self.assertEqual(first, 2)
        self.assertEqual(s.calls.count("ReadValue"), 3)

    def test_exact_steps_and_pause(self):
        s = FakeSession()
        self.assertEqual(s.advance(5)["frame"], 15)
        self.assertEqual(s.calls.count("GetGameState"), 5)
        self.assertEqual(s.stable()["frame"], 15)

    def test_stop_prevents_release(self):
        s = FakeSession(); s.stop.set()
        self.assertEqual(s.advance(5)["frame"], 10)
        self.assertNotIn("GetGameState", s.calls)

    def test_focus_failure_prevents_release(self):
        s = FakeSession()
        with self.assertRaises(BridgeError): s.advance(1, guard=lambda: False)
        self.assertNotIn("GetGameState", s.calls)

    def test_unexpected_increment_halts_without_retry(self):
        s = FakeSession(); s.increment = 2
        with self.assertRaises(BridgeError): s.advance(5)
        self.assertTrue(s.failed)
        self.assertEqual(s.calls.count("GetGameState"), 1)
        with self.assertRaises(BridgeError): s.observe()

    def test_single_step_required(self):
        s = FakeSession(); s.single_step = False
        with self.assertRaises(BridgeError): s.observe()
        self.assertNotIn("GetGameState", s.calls)

    def test_bounds(self):
        for frames in (0, 121, -1, True, 1.5):
            with self.assertRaises(ValueError): FakeSession().advance(frames)

    def test_capture_same_frame(self):
        s = FakeSession()
        with patch("rts_controller.paused.capture", return_value={"width": 2560, "height": 1440}):
            result = s.capture("DP-1", "ignored.png")
        self.assertEqual(result["simulation_frame"], 10)
        self.assertEqual(result["image"]["width"], 2560)
        self.assertNotIn("GetGameState", s.calls)

    def test_capture_race_rejected(self):
        s = FakeSession()
        def capture(*args): s.frame += 1; return {}
        with patch("rts_controller.paused.capture", side_effect=capture):
            with self.assertRaises(BridgeError): s.capture("DP-1", "ignored.png")

    def test_move_rejects_unowned_actor(self):
        with self.assertRaises(BridgeError): move(FakeSession(), Mock(), "999", (256, 512))

    def test_move_rejects_far_destination(self):
        with self.assertRaises(BridgeError): move(FakeSession(), Mock(), "100", (5000, 512))

    def test_move_selection_then_arrival(self):
        s = FakeSession()
        snapshot = s.observe()
        snapshot["own_objects"][0]["selected"] = False
        s.stable = Mock(side_effect=lambda: snapshot)
        g = Mock(); g.focused.return_value = True
        def order(name, fields, **kwargs):
            if name == "UnitCommand": snapshot["own_objects"][0]["selected"] = True
            else: snapshot["own_objects"][0]["coordinates"] = {"x": 512, "y": 512}
        with patch("rts_controller.paused_move.Orders") as factory:
            factory.return_value.request.side_effect = order
            self.assertEqual(move(s, g, "100", (512, 512))["status"], "arrived")
            self.assertEqual(factory.return_value.request.call_count, 2)

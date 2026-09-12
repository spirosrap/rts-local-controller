import time
import itertools
import unittest
from unittest.mock import Mock, patch
from rts_controller.ra2_move import MoveAdapter
from rts_controller.ra2 import BridgeError


class MoveTests(unittest.TestCase):
    def adapter(self, selected=False):
        reader = Mock()
        reader.port = 14521
        frames = itertools.count(1)
        reader.observe.side_effect = lambda: {
            "frame": next(frames), "single_human": True, "observed_at": time.monotonic(), "own_objects": [
                {"id": "100", "coordinates": {"x": 1000, "y": 1000},
                 "health": 100, "on_map": True, "in_limbo": False, "selected": selected}]}
        adapter = MoveAdapter(reader, "100", 1, (1256, 1000), armed=True)
        adapter.orders = Mock()
        return adapter, reader

    def test_arming_required(self):
        with self.assertRaises(ValueError): MoveAdapter(Mock(), "100", 1, (1, 1))

    def test_finished_or_multiple_human_session_refused(self):
        for flags in ({"single_human": False}, {"winner": True}, {"loser": True}):
            a, r = self.adapter()
            snapshot = r.observe(); snapshot.update(flags)
            frames = itertools.count(1)
            r.observe.side_effect = lambda: {**snapshot, "frame": next(frames)}
            with self.assertRaises(BridgeError): a.observe()
            r._request.assert_not_called()
            a.orders.request.assert_not_called()

    def test_paused_session_refused(self):
        a, r = self.adapter()
        snapshot = r.observe()
        r.observe.side_effect = None; r.observe.return_value = snapshot
        with self.assertRaisesRegex(BridgeError, "not advancing"): a.observe()
        a.orders.request.assert_not_called()

    def test_unowned_and_long_moves_rejected(self):
        a, r = self.adapter(); a.actor = "200"
        with self.assertRaises(BridgeError): a.observe()
        a, r = self.adapter(); a.destination = (5000, 1000)
        with self.assertRaises(BridgeError): a.observe()
        r._request.assert_not_called()

    def test_focus_loss_prevents_input(self):
        a, r = self.adapter()
        with patch.object(a, "focused", return_value=False):
            with self.assertRaises(BridgeError): a.execute({"kind": "select", "actor": "100"})
        r._request.assert_not_called()

    def test_selected_owned_move_payload(self):
        a, r = self.adapter(selected=True)
        with patch.object(a, "focused", return_value=True):
            a.execute({"kind": "move", "actor": "100", "destination": (1256, 1000)})
        a.orders.request.assert_called_once_with("MissionClicked", {
            "objectAddresses": [100], "event": "Mission_Move",
            "coordinates": {"x": 1256, "y": 1000, "z": 0}})

    def test_attack_is_unavailable(self):
        a, r = self.adapter()
        with self.assertRaises(BridgeError): a.execute({"kind": "attack", "actor": "100"})
        r._request.assert_not_called()

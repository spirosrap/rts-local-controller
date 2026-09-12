import threading
import unittest
from rts_controller.core import Controller, Order, State, Unit
from rts_controller.runner import run


def state(seq=0, selected=None, **overrides):
    values = dict(sequence=seq, captured_at=10., focused=True, selected=selected,
                  units={"tanya": Unit("tanya", 0, 0), "ship": Unit("ship", 20, 20)})
    values.update(overrides)
    return State(**values)


class ControlTests(unittest.TestCase):
    def controller(self): return Controller(Order("tanya", "attack", target="ship"))

    def test_selection_is_confirmed_before_attack(self):
        c = self.controller()
        self.assertEqual(c.step(state(), 10)["kind"], "select")
        self.assertIsNone(c.step(state(1), 10))
        self.assertEqual(c.step(state(2, "tanya"), 10)["kind"], "attack")
        self.assertIsNone(c.step(state(3, "tanya"), 10))
        self.assertEqual(c.phase, "executing")
        c.step(state(4, "tanya", destroyed=frozenset({"ship"})), 10)
        self.assertEqual(c.phase, "done")

    def test_disappearing_target_is_not_success(self):
        c = self.controller()
        c.step(state(units={"tanya": Unit("tanya", 0, 0)}), 10)
        self.assertEqual(c.phase, "halted")

    def test_guards(self):
        for overrides in ({"focused": False}, {"captured_at": 8.},
                          {"captured_at": 11.}, {"captured_at": float("nan")},
                          {"units": {}}):
            with self.subTest(overrides=overrides):
                c = self.controller()
                self.assertIsNone(c.step(state(**overrides), 10))
                self.assertEqual(c.phase, "halted")

    def test_duplicate_observation_cannot_confirm_selection(self):
        c = self.controller()
        c.step(state(), 10)
        self.assertIsNone(c.step(state(selected="tanya"), 10))
        self.assertEqual(c.phase, "selecting")

    def test_timeout_and_stop(self):
        c = self.controller(); c.step(state(), 10)
        c.step(state(1, captured_at=30), 30)
        self.assertEqual(c.phase, "halted")
        c = self.controller(); c.step(state(), 10, stopped=True)
        self.assertEqual(c.phase, "halted")

    def test_move_completes_on_arrival(self):
        c = Controller(Order("tanya", "move", destination=(20, 20)))
        c.step(state(), 10)
        c.step(state(1, "tanya"), 10)
        c.step(state(2, "tanya", units={"tanya": Unit("tanya", 20, 20)}), 10)
        self.assertEqual(c.phase, "done")

    def test_release_on_adapter_failure(self):
        class Broken:
            released = False
            def observe(self): raise RuntimeError("test")
            def release(self): self.released = True
        adapter = Broken()
        with self.assertRaises(RuntimeError): run(self.controller(), adapter, threading.Event())
        self.assertTrue(adapter.released)

    def test_preexisting_stop_sends_no_input(self):
        class Stopped:
            released = False
            def observe(self): raise AssertionError("Must not observe")
            def execute(self, action): raise AssertionError("Must not act")
            def release(self): self.released = True
        stop = threading.Event(); stop.set(); adapter = Stopped()
        self.assertEqual(run(self.controller(), adapter, stop), "halted")
        self.assertTrue(adapter.released)


if __name__ == "__main__": unittest.main()

import json
import unittest
from unittest.mock import patch
from rts_controller.test_game import TestGame, require_private_network, desktop_unlocked
from rts_controller.ra2 import BridgeError


class GuardTests(unittest.TestCase):
    def test_lock_on_any_monitor_blocks(self):
        self.assertFalse(desktop_unlocked([{"solitaryBlockedBy": []}, {"solitaryBlockedBy": ["LOCK"]}]))

    def test_unknown_lock_state_blocks(self):
        for monitors in (None, [], [{}], [None], [{"solitaryBlockedBy": "LOCK"}],
                         [{"solitaryBlockedBy": ["WORKSPACE"]}]):
            with self.subTest(monitors=monitors):
                self.assertFalse(desktop_unlocked(monitors))

    def test_readable_unlocked_monitor(self):
        self.assertTrue(desktop_unlocked([{"solitaryBlockedBy": ["WINDOW"]}]))

    def test_lock_overrides_stale_game_focus(self):
        game = object.__new__(TestGame); game.pid = 42
        with patch.object(game, "valid", return_value=True), patch("subprocess.check_output",
                return_value=b'[{"solitaryBlockedBy":["LOCK"]}]') as query:
            self.assertFalse(game.focused())
            self.assertEqual(query.call_count, 1)

    def test_external_interfaces_rejected(self):
        with patch("subprocess.check_output", return_value=b'[{"ifname":"lo"},{"ifname":"eth0"}]'):
            with self.assertRaises(BridgeError): require_private_network()

    def test_loopback_namespace_accepted(self):
        with patch("subprocess.check_output", return_value=b'[{"ifname":"lo"}]'):
            require_private_network()

    def test_monitor_mapping(self):
        game = object.__new__(TestGame); game.pid = 42
        monitor = {"name":"DP-1","id":1,"width":2560,"height":1440,"scale":1,"x":2560,"y":0}
        window = {"pid":42,"title":"Red Alert 2","monitor":1,"at":[2560,0],"size":[2560,1440]}
        with patch.object(game,"focused",return_value=True), patch("subprocess.check_output",
                side_effect=[json.dumps([monitor]).encode(),json.dumps([window]).encode()]):
            self.assertTrue(game.fits_output("DP-1"))
        window["at"] = [0, 0]
        with patch.object(game,"focused",return_value=True), patch("subprocess.check_output",
                side_effect=[json.dumps([monitor]).encode(),json.dumps([window]).encode()]):
            self.assertFalse(game.fits_output("DP-1"))

    def test_invalid_identity_never_terminated(self):
        game = object.__new__(TestGame); game.pid = 42
        with patch.object(game,"valid",return_value=False), patch("os.pidfd_open") as opened:
            game.terminate_uncertain()
            opened.assert_not_called()

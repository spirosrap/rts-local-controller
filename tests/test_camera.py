import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
from rts_controller.camera import center, center_key, send_key
from rts_controller.ra2 import BridgeError


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        (self.path / 'KeyboardMD.ini').write_text('[Hotkeys]\nCenterView=12\nFollow=70\n')
        self.game = Mock(directory=self.path)
        self.game.fits_output.return_value = True
        self.session = Mock(stop=threading.Event())
        self.state = {'frame': 10, 'single_human': True, 'winner': False, 'loser': False,
                      'own_objects': [{'id': '81', 'selected': True, 'health': 50,
                                       'on_map': True, 'in_limbo': False}]}
        self.session.stable.return_value = self.state
        self.session.advance.return_value = {**self.state, 'frame': 14}

    def test_uses_center_not_follow(self):
        self.assertEqual(center_key(self.path), 'KP_Begin')

    def test_unsupported_binding_refused(self):
        (self.path / 'KeyboardMD.ini').write_text('[Hotkeys]\nCenterView=70\n')
        with self.assertRaises(BridgeError): center_key(self.path)

    def test_dedicated_letter_binding(self):
        (self.path / 'KeyboardMD.ini').write_text('[Hotkeys]\nCenterView=74\n')
        self.assertEqual(center_key(self.path), 'j')

    def test_binding_collision_refused(self):
        (self.path / 'KeyboardMD.ini').write_text('[Hotkeys]\nCenterView=74\nOther=74\n')
        with self.assertRaises(BridgeError): center_key(self.path)

    def test_releases_after_step_failure(self):
        self.session.advance.side_effect = BridgeError('focus lost')
        sender = Mock()
        with self.assertRaises(BridgeError): center(self.session, self.game, 'DP-1', key_sender=sender)
        self.assertEqual([c.args[1] for c in sender.call_args_list], ['down', 'up'])

    def test_stop_does_not_send(self):
        self.session.stop.set(); sender = Mock()
        with self.assertRaises(BridgeError): center(self.session, self.game, 'DP-1', key_sender=sender)
        sender.assert_not_called()

    def test_missing_selection_does_not_send(self):
        self.state['own_objects'] = []; sender = Mock()
        with self.assertRaises(BridgeError): center(self.session, self.game, 'DP-1', key_sender=sender)
        sender.assert_not_called()

    def test_acknowledgment_not_visual_success(self):
        result = center(self.session, self.game, 'DP-1', key_sender=Mock())
        self.assertEqual(result['status'], 'camera_key_sent')
        self.assertIn('not camera proof', result['verification'])

    def test_no_arbitrary_keys(self):
        with self.assertRaises(ValueError): send_key('f', 'down')

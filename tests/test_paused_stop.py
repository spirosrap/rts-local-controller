import threading
import unittest
from unittest.mock import Mock, patch
from rts_controller.paused_stop import stop_actor
from rts_controller.ra2 import BridgeError


class StopTests(unittest.TestCase):
    def setUp(self):
        self.state = {'frame': 10, 'winner': False, 'loser': False, 'single_human': True,
                      'own_objects': [{'id':'55','type_id':'9','health':50,'on_map':True,
                                       'in_limbo':False,'mission':'Mission_Guard',
                                       'coordinates':{'x':256,'y':512}}]}
        self.s = Mock(stop=threading.Event())
        self.s.stable.side_effect = lambda: self.state
        def advance(*args, **kwargs):
            self.state['frame'] += 1
            return self.state
        self.s.advance.side_effect = advance
        self.g = Mock(); self.g.focused.return_value = True

    def test_unowned_rejected_before_order(self):
        with patch('rts_controller.paused_stop.Orders') as orders:
            with self.assertRaises(BridgeError): stop_actor(self.s,self.g,'99')
            orders.assert_not_called()

    def test_stop_latch_rejects_order(self):
        self.s.stop.set()
        with patch('rts_controller.paused_stop.Orders') as orders:
            with self.assertRaises(BridgeError): stop_actor(self.s,self.g,'55')
            orders.assert_not_called()

    def test_stable_guard_verifies_stop(self):
        with patch('rts_controller.paused_stop.Orders') as orders:
            result = stop_actor(self.s,self.g,'55')
            self.assertEqual(result['status'],'stop_verified')
            fields = orders.return_value.request.call_args.args[1]
            self.assertEqual(fields['coordinates'],{'x':256,'y':512})

    def test_ack_with_moving_mission_is_not_success(self):
        self.state['own_objects'][0]['mission'] = 'Mission_Move'
        with patch('rts_controller.paused_stop.Orders'):
            with self.assertRaises(BridgeError): stop_actor(self.s,self.g,'55',max_frames=5)

import copy
import unittest
from rts_controller.progress import changes
from rts_controller.ra2 import Reader, BridgeError
from test_ra2 import game


class ProgressTests(unittest.TestCase):
    def test_owned_types_and_economy(self):
        raw = game()
        raw['houses'][0]['money'] = 400
        raw['objects'][0]['pointerTechnotypeclass'] = 71
        raw['objectTypes'] = [{'pointerSelf': 71, 'name': 'ENGINEER'}]
        result = Reader().summarize(raw)
        self.assertEqual(result['own_objects'][0]['type_name'], 'ENGINEER')
        self.assertEqual(result['economy']['credits'], 400)
        self.assertEqual(len(result['own_objects']), 1)

    def test_missing_does_not_mean_destroyed(self):
        a = Reader().summarize(game()); b = copy.deepcopy(a); b['own_objects'] = []
        self.assertEqual(changes(a,b)['events'][0]['kind'], 'owned_object_missing')
        self.assertEqual(changes(a,b)['events'][0]['cause'], 'unknown')

    def test_health_and_position_changes(self):
        a = Reader().summarize(game()); b = copy.deepcopy(a)
        b['frame'] += 1; b['own_objects'][0]['health'] = 100
        b['own_objects'][0]['coordinates']['x'] += 100
        self.assertEqual({e['kind'] for e in changes(a,b)['events']},
                         {'health_changed', 'coordinates_changed'})

    def test_recycled_type_not_same_unit(self):
        a = Reader().summarize(game()); b = copy.deepcopy(a)
        b['own_objects'][0]['type_id'] = 'new'
        self.assertEqual(changes(a,b)['events'], [{'kind':'identity_changed','actor':'100'}])

    def test_frame_reset_refused(self):
        with self.assertRaises(BridgeError): changes({'frame':10}, {'frame':9})

    def test_unchanged_state_has_no_events(self):
        a = Reader().summarize(game())
        self.assertEqual(changes(a,a)['events'], [])

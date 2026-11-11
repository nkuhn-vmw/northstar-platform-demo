import unittest
from unittest.mock import patch

from northstar_kit.cf import CF, CFError


class WaitAppTests(unittest.TestCase):
    def test_transient_crash_can_recover(self):
        cf = CF(timeout=10)
        with patch.object(cf, 'list', return_value=[{'type': 'web', 'guid': 'process'}]), \
             patch.object(cf, 'api', side_effect=[{'resources': [{'state': 'CRASHED'}]},
                                                 {'resources': [{'state': 'RUNNING'}]}]), \
             patch('northstar_kit.cf.time.sleep'):
            cf.wait_app('app')

    def test_timeout_reports_safe_last_state_and_log_guidance(self):
        for state, expected in [('CRASHED', 'CRASHED'), ('STARTING', 'STARTING'),
                                ('sensitive broker detail', 'UNKNOWN')]:
            with self.subTest(state=state):
                cf = CF(timeout=0)
                with patch.object(cf, 'list', return_value=[{'type': 'web', 'guid': 'process'}]), \
                     patch.object(cf, 'api', return_value={'resources': [{'state': state}]}):
                    with self.assertRaises(CFError) as caught:
                        cf.wait_app('app')
                self.assertIn('last observed: ' + expected, str(caught.exception))
                self.assertIn('cf logs <app-name> --recent', str(caught.exception))
                self.assertNotIn('sensitive broker detail', str(caught.exception))

    def test_timeout_distinguishes_missing_process_and_statistics(self):
        for processes, expected in [([], 'no web process'),
                                   ([{'type': 'web', 'guid': 'p'}], 'no web instance statistics')]:
            with self.subTest(expected=expected):
                with patch.object(CF, 'list', return_value=processes), \
                     patch.object(CF, 'api', return_value={'resources': []}):
                    with self.assertRaisesRegex(CFError, expected):
                        CF(timeout=0).wait_app('app')

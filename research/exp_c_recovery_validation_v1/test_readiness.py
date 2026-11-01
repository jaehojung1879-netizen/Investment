"""Calendar/synthetic metadata only; never load market observations."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import readiness
import run


class ReadinessTests(unittest.TestCase):
    def test_sparse_counterexample(self):
        import pandas as pd
        days = pd.bdate_range('1990-01-03', periods=9033)
        result = readiness.calendar_bound(days, range(4200, 9030, 5))
        self.assertLess(result['witness_stressed_rows'], result['all_complete_mature_rows'])
        self.assertEqual(result['upper_bound_blocks'], result['witness_support']['occupied_126_session_blocks'])

    def test_prepare_no_lock_or_values(self):
        with patch.object(sys, 'argv', ['run.py', '--prepare']), patch.object(run, 'freeze_identity', return_value='SYNTHETIC'), patch.object(run, 'runtime_gate'), patch.object(run, 'api', side_effect=AssertionError('network')), patch.object(run, 'prepare_sources', side_effect=AssertionError('values')):
            self.assertEqual(run.main(), 0)

    @unittest.skipUnless(importlib.util.find_spec('exchange_calendars') and importlib.util.find_spec('korean_lunar_calendar'), 'pinned calendar dependencies unavailable')
    def test_exact_calendar_upper_bound(self):
        import contextlib
        import io
        import json
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            readiness.main()
        result = json.loads(stream.getvalue())
        self.assertEqual(result['upper_bound_blocks'], 33)
        self.assertEqual(result['weekly_decisions'], 1027)
        self.assertEqual(result['all_complete_mature_rows'], 1014)
        self.assertEqual(result['witness_stressed_rows'], 45)
        self.assertEqual(result['first_possible_test'], '2010-06-18')

from fractions import Fraction
import json

from candidate.store import load_candidate
from demo import CHANNEL, STATION, seed_demo
from inspection.receipts import list_pending_receipts
from inspection.standards import CheckStandard, load_check_standard, register_check_standard
from source.calibrations import load_calibration
from source.registry import StationRegistry
from source.revisions import load_revision
from tests.fixtures import StationCase


class DailyFlowTests(StationCase):
    def test_calibrated_rows(self):
        snapshot = self.prepare('R0')
        signed = self.sign('R0')
        self.assertIsNotNone(signed)
        self.assertEqual([r.value for r in snapshot.rows[:3]], [Fraction(7, 4), Fraction(1, 4), None])
        self.assertEqual(signed.report, snapshot)
        self.assertEqual(self.current(), signed)
        self.assertEqual(self.issue_count(), 1)
        self.assertEqual(signed.receipt.issue_id, 'issue:R0')
        actual = [None if row.value is None else str(row.value) for row in snapshot.rows[:3]]
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'daily_exact', 'input': {'raw': [3, 0, None], 'scale': '1/2', 'offset': '1/4'},
            'expected': ['7/4', '1/4', None], 'actual': actual,
            'downstream_expected': 'issue:R0', 'downstream_actual': self.current().receipt.issue_id,
            'code_paths': ['candidate/convert.py', 'candidate/assemble.py', 'publication/issue.py', 'receipt/lookup.py'],
            'oracle': 'Compute 3/2 + 1/4 and 0 + 1/4 by hand and carry null through separately.',
        }, sort_keys=True))

    def test_repeated_initialization(self):
        custom = CheckStandard('zero', CHANNEL, 'zero-trial', 'mm', 0, '-1/2', '1/2')
        register_check_standard(self.station, STATION, custom)
        signed = self.sign(self.prepare('R0').candidate_id)
        old = self.prepare('R1', calibration='C3', corrects='day-R0')
        accepted = self.select('R1')
        pending = self.inspect('R1', 'zero')
        self.reopen()
        seed_demo(self.station)
        self.reopen()
        self.assertEqual(load_check_standard(self.station, STATION, 'zero'), custom)
        self.assertEqual(StationRegistry(self.station).require_channel(STATION, CHANNEL).input_unit, 'mV')
        self.assertEqual(load_calibration(self.station, 'C3').offset, 0)
        self.assertEqual(load_revision(self.station, 'day-R1').corrects, 'day-R0')
        self.assertEqual(load_candidate(self.station, 'R1'), old)
        self.assertEqual(list_pending_receipts(self.station), (pending,))
        self.assertEqual(self.select('R1'), accepted)
        self.assertEqual(self.current(), signed)
        self.assertEqual(self.issue_count(), 1)

    def test_row_identity(self):
        frozen = self.prepare('R0')
        original = load_revision(self.station, 'day-R0')
        signed = self.sign('R0')
        names = ['reading', 'zero-trial', 'gap', 'mid', 'span-trial', 'repeat']
        for rows in (original.samples, frozen.rows, signed.report.rows):
            self.assertEqual([row.sample_id for row in rows], names)
            self.assertEqual([row.position for row in rows], list(range(6)))
        self.assertEqual([signed.report.rows[i].value for i in (0, 5)], [Fraction(7, 4)] * 2)
        self.assertEqual([signed.report.rows[i].calibration_id for i in (0, 5)], ['C1', 'C1'])

    def test_zero_trial(self):
        self.prepare('R0')
        zero = self.inspect('R0', 'zero')
        self.assertTrue(zero.passed)
        self.assertEqual((zero.finding.position, zero.finding.value), (1, Fraction(1, 4)))
        self.assertEqual(zero.standard.upper, Fraction(1, 4))
        self.assertEqual(self.sign('R0').receipt.zero_receipt_id, 'R0-zero')

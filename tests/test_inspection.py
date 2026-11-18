from dataclasses import replace
from fractions import Fraction

from demo import trial_samples
from inspection.receipts import inspect_candidate, load_check_receipt
from publication.admission import deliver_receipt
from tests.fixtures import StationCase


class InspectionTests(StationCase):
    def test_span_failure_prevents_issue(self):
        self.prepare('R0', span=4)
        self.assertTrue(self.inspect('R0', 'zero').passed)
        span = self.inspect('R0', 'span')
        self.assertEqual(span.finding.value, Fraction(9, 4))
        self.assertEqual(span.finding.reason, 'above_span')
        self.assertFalse(span.passed)
        self.assertEqual(self.send('R0', 'span').status, 'waiting')
        self.assertEqual(self.send('R0', 'zero').status, 'waiting')
        self.assertEqual(load_check_receipt(self.station, 'R0-span'), span)
        self.assertIsNone(self.history('R0'))
        self.assertIsNone(self.current())
        self.assertEqual(self.issue_count(), 0)

    def test_span_upper_endpoint(self):
        self.prepare('R0', span='7/2')
        span = self.inspect('R0', 'span')
        self.assertEqual(span.finding.value, 2)
        self.assertTrue(span.passed)
        self.assertEqual(self.sign('R0').receipt.span_receipt_id, 'R0-span')
        self.assertEqual(self.issue_count(), 1)

    def test_missing_trial(self):
        cases = [('R0', 'span', [row for row in trial_samples() if row[0] != 'span-trial'], 'missing_sample'),
                 ('R1', 'zero', [row for row in trial_samples() if row[0] != 'zero-trial'], 'missing_sample'),
                 ('R2', 'span', trial_samples(None), 'missing_value')]
        for candidate, kind, samples, reason in cases:
            with self.subTest(candidate=candidate, kind=kind):
                self.prepare(candidate, samples=samples)
                self.select(candidate)
                receipt = self.inspect(candidate, kind)
                self.assertFalse(receipt.passed)
                self.assertEqual(receipt.finding.reason, reason)
                self.assertIsNone(receipt.finding.value)
                self.assertEqual(self.send(candidate, kind).status, 'waiting')
                self.assertIsNone(self.sign(candidate))
                self.assertEqual(load_check_receipt(self.station, receipt.receipt_id), receipt)
        self.assertEqual(self.issue_count(), 0)

    def test_conflicting_receipts_and_evidence(self):
        snapshot = self.prepare('R0')
        other = self.prepare('R1', calibration='C2')
        zero = self.inspect('R0', 'zero')
        self.assertEqual(inspect_candidate(self.station, 'R0', 'zero', 'alternate'), zero)
        with self.assertRaises(ValueError):
            inspect_candidate(self.station, 'R1', 'zero', zero.receipt_id)
        with self.assertRaises(ValueError):
            deliver_receipt(self.publication, zero, other)
        with self.assertRaises(ValueError):
            deliver_receipt(self.publication, replace(zero, finding=replace(zero.finding, position=0)), snapshot)
        self.assertEqual(deliver_receipt(self.publication, zero, snapshot).status, 'waiting')
        self.assertEqual(deliver_receipt(self.publication, zero).status, 'waiting')
        with self.assertRaises(ValueError):
            deliver_receipt(self.publication, replace(zero, receipt_id='alternate'), snapshot)
        self.assertIsNone(self.current())
        self.assertIsNotNone(self.sign('R0'))

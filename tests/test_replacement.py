from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from functools import partial
from threading import Event

from candidate.replace import replace_candidate
from candidate.snapshot import snapshot_digest
from demo import DAY, STATION
from inspection.delivery import redeliver_receipt
from publication.admission import admit_replacement, deliver_receipt
from publication.ledger import open_publication
from source.database import open_station
from tests.fixtures import StationCase


MARKER = 'DAILY_REPORT_WRONG_REVISION'


class ReplacementTests(StationCase):
    def _old_in_inspection(self):
        prior = self.sign(self.prepare('R0').candidate_id)
        old = self.prepare('R1', corrects='day-R0')
        self.select('R1')
        self.inspect('R1', 'zero')
        self.inspect('R1', 'span')
        self.assertEqual(self.send('R1', 'zero').status, 'waiting')
        return prior, old

    def _assert_prior_only(self, prior):
        self.assertEqual(self.current(), prior, MARKER)
        self.assertIsNone(self.history('R1'), MARKER)
        self.assertIsNone(self.history('R2'), MARKER)
        self.assertEqual(self.issue_count(), 1, MARKER)

    def test_late_check_cannot_issue_replaced_candidate(self):
        prior, _ = self._old_in_inspection()
        self.prepare('R2', calibration='C3', corrects='day-R1')
        self.select('R2')
        self.inspect('R2', 'zero')
        self.inspect('R2', 'span')
        self.assertEqual(self.send('R1', 'span').status, 'retired', MARKER)
        self.assertEqual(self.send('R2', 'zero').status, 'waiting', MARKER)
        self._assert_prior_only(prior)
        updated = self.send('R2', 'span').issue
        self.assertIsNotNone(updated, MARKER)
        self.assertEqual(updated.receipt.issue_id, 'issue:R2')
        self.assertEqual(updated.receipt.zero_receipt_id, 'R2-zero')
        self.assertEqual(updated.receipt.span_receipt_id, 'R2-span')
        self.reopen()
        for name, kind in [('R2', 'span'), ('R2', 'zero'), ('R1', 'span'), ('R1', 'zero'), ('R0', 'span'), ('R0', 'zero')]:
            self.send(name, kind)
        self.assertEqual(self.issue_count(), 2)
        self.assertEqual(self.current(), updated)
        self.assertEqual(self.history('R0'), prior)
        self.assertIsNone(self.history('R1'))

    def test_equal_values_do_not_share_checks(self):
        prior, old = self._old_in_inspection()
        new = self.prepare('R2', calibration='C2', corrects='day-R1')
        self.assertEqual(old.value_digest, new.value_digest)
        self.assertNotEqual(snapshot_digest(old), snapshot_digest(new))
        self.select('R2')
        self.inspect('R2', 'zero')
        self.inspect('R2', 'span')
        self.send('R2', 'zero')
        self._assert_prior_only(prior)
        self.assertEqual(self.send('R1', 'span').status, 'retired', MARKER)
        self.assertEqual(self.send('R2', 'zero').status, 'waiting', MARKER)
        self._assert_prior_only(prior)
        result = self.send('R2', 'span')
        self.assertEqual(result.issue.report, new)
        self.assertEqual(result.issue.receipt.span_receipt_id, 'R2-span')
        self.assertEqual(self.send('R2', 'zero').issue, result.issue)
        self.assertEqual(self.issue_count(), 2)

    def test_prior_signed_report_remains_readable(self):
        self._old_in_inspection()
        old = self.send('R1', 'span').issue
        self.prepare('R2', calibration='C3', corrects='day-R1')
        self.select('R2')
        self.assertEqual(self.current(), old)
        new = self.sign('R2')
        self.assertEqual(self.send('R1', 'zero').issue, old)
        self.close_station()
        self.assertEqual(self.current(), new)
        self.assertEqual(self.history('R1'), old)
        self.assertEqual(self.history('R1').report.rows[0].calibration_id, 'C1')
        self.assertEqual(self.current().report.rows[0].calibration_id, 'C3')
        self.assertEqual(self.issue_count(), 3)

    def _send_old_span_on_worker(self, **hooks):
        with closing(open_station(self.station_path)) as station, closing(open_publication(self.publication_path)) as publication:
            return redeliver_receipt(station, 'R1-span', partial(deliver_receipt, publication, **hooks))

    def test_inflight_old_issue_replacement_first(self):
        prior, _ = self._old_in_inspection()
        self.prepare('R2', corrects='day-R1')
        paused = Event()
        resume = Event()

        def pause_before_decision():
            paused.set()
            if not resume.wait(10):
                raise TimeoutError('old issue was not resumed')

        with ThreadPoolExecutor(max_workers=1) as pool:
            finishing = pool.submit(self._send_old_span_on_worker, before_decision=pause_before_decision)
            try:
                self.assertTrue(paused.wait(5))
                self.assertEqual(self.select('R2').previous_candidate_id, 'R1')
                self.assertEqual(self.current(), prior)
            finally:
                resume.set()
            self.assertEqual(finishing.result(timeout=10).status, 'retired', MARKER)
        self._assert_prior_only(prior)
        self.assertIsNotNone(self.sign('R2'))

    def test_inflight_old_issue_issue_first(self):
        prior, _ = self._old_in_inspection()
        self.prepare('R2', corrects='day-R1')
        at_commit = Event()
        at_replacement = Event()
        resume = Event()

        def pause_before_commit():
            at_commit.set()
            if not resume.wait(10):
                raise TimeoutError('old issue commit was not resumed')

        def select_on_worker():
            with closing(open_station(self.station_path)) as station, closing(open_publication(self.publication_path)) as publication:
                return replace_candidate(station, STATION, DAY, 'R2', 'select-R2',
                                         partial(admit_replacement, publication, before_decision=at_replacement.set))

        with ThreadPoolExecutor(max_workers=2) as pool:
            finishing = pool.submit(self._send_old_span_on_worker, before_commit=pause_before_commit)
            try:
                self.assertTrue(at_commit.wait(5))
                selecting = pool.submit(select_on_worker)
                self.assertTrue(at_replacement.wait(5))
                self.assertEqual(self.current(), prior)
                self.assertIsNone(self.history('R1'))
            finally:
                resume.set()
            old = finishing.result(timeout=10).issue
            self.assertEqual(selecting.result(timeout=10).previous_candidate_id, 'R1')
        self.assertIsNotNone(old)
        self.assertEqual(self.current(), old)
        self.assertEqual(self.history('R1'), old)
        self.assertEqual(self.issue_count(), 2)
        self.assertEqual(self.sign('R2').receipt.issue_id, 'issue:R2')
        self.assertEqual(self.history('R1'), old)

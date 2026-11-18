from contextlib import closing
from functools import partial

from candidate.requests import load_replacement_request
from demo import DAY, STATION
from inspection.delivery import send_pending_receipts
from inspection.receipts import list_pending_receipts
from publication.admission import admit_replacement, deliver_receipt
from publication.eligibility import find_active_candidate
from publication.ledger import open_publication
from receipt.lookup import read_report
from tests.fixtures import LostReply, StationCase, lose_reply


class CommitFailure(Exception):
    pass


class IssueTests(StationCase):
    def _next_issue(self):
        prior = self.sign(self.prepare('R0').candidate_id)
        self.prepare('R1', calibration='C3', corrects='day-R0')
        self.select('R1')
        self.inspect('R1', 'zero')
        self.inspect('R1', 'span')
        self.assertEqual(self.send('R1', 'zero').status, 'waiting')
        return prior

    def test_failed_commit_preserves_prior_view(self):
        prior = self._next_issue()

        def fail_commit():
            raise CommitFailure('simulated interruption before durable issue')

        with self.assertRaises(CommitFailure):
            self.send('R1', 'span', port=partial(deliver_receipt, self.publication, before_commit=fail_commit))
        self.reopen()
        self.assertEqual(self.current(), prior)
        self.assertEqual(self.history('R0'), prior)
        self.assertIsNone(self.history('R1'))
        self.assertEqual(self.issue_count(), 1)
        self.assertEqual([item.receipt_id for item in list_pending_receipts(self.station)], ['R1-span'])
        issued = self.send('R1', 'span').issue
        self.assertIsNotNone(issued)
        self.assertEqual(self.history('R1'), issued)
        self.assertEqual(self.current(), issued)
        self.assertEqual(self.issue_count(), 2)

    def test_rollback_visibility(self):
        prior = self._next_issue()

        def inspect_uncommitted_then_fail():
            self.assertEqual(self.history('R1').receipt.issue_id, 'issue:R1')
            with closing(open_publication(self.publication_path)) as reader:
                self.assertEqual(read_report(reader, station=STATION, day=DAY), prior)
                self.assertIsNone(read_report(reader, issue_id='issue:R1'))
                self.assertEqual(reader.execute('SELECT count(*) FROM issues').fetchone()[0], 1)
            raise CommitFailure('abort first issue after writing its records')

        with self.assertRaises(CommitFailure):
            self.send('R1', 'span', port=partial(deliver_receipt, self.publication,
                                                before_commit=inspect_uncommitted_then_fail))
        self.assertIsNone(self.history('R1'))
        self.assertEqual(self.current(), prior)
        self.assertEqual(self.issue_count(), 1)

    def test_lost_success_reply_replays(self):
        self.sign(self.prepare('R0').candidate_id)
        self.prepare('R1', corrects='day-R0')
        with self.assertRaises(LostReply) as replaced:
            self.select('R1', port=lose_reply(partial(admit_replacement, self.publication)))
        self.assertIsNone(load_replacement_request(self.station, 'select-R1')[1])
        self.reopen()
        self.assertEqual(self.select('R1'), replaced.exception.args[0])
        self.inspect('R1', 'zero')
        self.inspect('R1', 'span')
        self.send('R1', 'span')
        with self.assertRaises(LostReply) as issued:
            self.send('R1', 'zero', port=lose_reply(partial(deliver_receipt, self.publication)))
        self.reopen()
        self.assertEqual(self.send('R1', 'zero'), issued.exception.args[0])
        self.assertEqual(self.send('R1', 'span').issue, self.current())
        self.assertEqual(self.issue_count(), 2)
        self.assertEqual(self.publication.execute('SELECT count(*) FROM admitted_replacements').fetchone()[0], 1)

    def test_pending_delivery(self):
        self.prepare('R0')
        zero = self.inspect('R0', 'zero')
        span = self.inspect('R0', 'span')
        with self.assertRaises(LostReply):
            self.send('R0', 'zero', port=lose_reply(partial(deliver_receipt, self.publication)))
        self.reopen()
        self.assertEqual(set(list_pending_receipts(self.station)), {zero, span})
        results = send_pending_receipts(self.station, partial(deliver_receipt, self.publication))
        self.assertEqual({result.receipt_id for result in results}, {'R0-zero', 'R0-span'})
        self.assertEqual(list_pending_receipts(self.station), ())
        self.assertEqual(self.current().receipt.issue_id, 'issue:R0')
        self.assertEqual(self.issue_count(), 1)

    def test_replay_after_later_request(self):
        prior = self.sign(self.prepare('R0').candidate_id)
        self.prepare('R1', corrects='day-R0')
        self.prepare('R2', corrects='day-R1')
        with self.assertRaises(LostReply) as first:
            self.select('R1', port=lose_reply(partial(admit_replacement, self.publication)))
        later = self.select('R2')
        self.assertEqual(later.previous_candidate_id, 'R1')
        self.reopen()
        self.assertEqual(self.select('R1'), first.exception.args[0])
        self.assertEqual(find_active_candidate(self.publication, STATION, DAY), 'R2')
        self.assertEqual(self.current(), prior)
        self.assertIsNone(self.sign('R1'))
        self.assertEqual(self.issue_count(), 1)
        self.assertEqual(self.sign('R2').receipt.issue_id, 'issue:R2')
        self.assertEqual(self.select('R2'), later)
        with self.assertRaises(ValueError):
            self.select('R2', request_id='select-R1')
        self.assertEqual(self.issue_count(), 2)

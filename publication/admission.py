from dataclasses import dataclass

from candidate.requests import ReplacementRequest, ReplacementResult
from candidate.snapshot import snapshot_digest
from inspection.receipts import CheckReceipt
from publication.eligibility import (can_issue, find_active_candidate, initialize_eligibility,
                                     is_retired, queue_replacement, select_on_delivery)
from publication.evidence import initialize_evidence, load_received_candidate, pin_candidate, record_evidence
from publication.issue import issue_if_eligible
from publication.ledger import IssueRecord, initialize_ledger, write_transaction
from source.registry import require_name


@dataclass(frozen=True)
class DeliveryResult:
    receipt_id: str
    status: str
    issue: IssueRecord | None = None


def initialize_publication(db):
    initialize_evidence(db)
    initialize_eligibility(db)
    initialize_ledger(db)
    db.execute('''
        CREATE TABLE IF NOT EXISTS admitted_replacements (
            request_id TEXT PRIMARY KEY,
            request_body TEXT NOT NULL,
            previous_candidate_id TEXT REFERENCES received_candidates(candidate_id)
        )
    ''')


def admit_replacement(db, request, snapshot, *, before_decision=None):
    if not isinstance(request, ReplacementRequest):
        raise ValueError('expected a named replacement request')
    require_name(request.request_id)
    if (request.station, request.day, request.candidate_id, request.input_digest) != (
        snapshot.station, snapshot.day, snapshot.candidate_id, snapshot_digest(snapshot)
    ):
        raise ValueError('replacement request differs from the fixed candidate')
    if before_decision is not None:
        before_decision()
    with write_transaction(db):
        fixed = pin_candidate(db, snapshot)
        previous = find_active_candidate(db, fixed.station, fixed.day)
        queue_replacement(db, fixed)
        return ReplacementResult(request, previous)


def deliver_receipt(db, receipt, snapshot=None, *, before_decision=None, before_commit=None):
    if not isinstance(receipt, CheckReceipt):
        raise ValueError('expected a fixed check receipt')
    if before_decision is not None:
        before_decision()
    with write_transaction(db):
        fixed = (load_received_candidate(db, receipt.candidate_id) if snapshot is None
                 else pin_candidate(db, snapshot))
        record_evidence(db, fixed, receipt)
        select_on_delivery(db, fixed)
        issue, created = issue_if_eligible(db, fixed)
        if issue is not None:
            if created and before_commit is not None:
                before_commit()
            return DeliveryResult(receipt.receipt_id, 'issued', issue)
        if is_retired(db, fixed.candidate_id):
            return DeliveryResult(receipt.receipt_id, 'retired')
        status = 'waiting' if can_issue(db, fixed) else 'not_selected'
        return DeliveryResult(receipt.receipt_id, status)

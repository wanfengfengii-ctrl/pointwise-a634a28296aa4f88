from dataclasses import dataclass

from candidate.requests import ReplacementRequest, ReplacementResult
from candidate.snapshot import canonical_json, snapshot_digest
from inspection.receipts import CheckReceipt
from publication.eligibility import (can_issue, initialize_eligibility, is_retired,
                                     select_candidate, select_on_delivery)
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


def _request_body(request):
    return canonical_json({
        'request_id': request.request_id, 'station': request.station, 'day': request.day,
        'candidate_id': request.candidate_id, 'input_digest': request.input_digest,
    })


def _admitted_replacement(db, request):
    row = db.execute(
        'SELECT request_body, previous_candidate_id FROM admitted_replacements WHERE request_id = ?',
        (request.request_id,),
    ).fetchone()
    if row is None:
        return None
    if row['request_body'] != _request_body(request):
        raise ValueError(f'conflicting replacement request {request.request_id}')
    return ReplacementResult(request, row['previous_candidate_id'])


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
    body = _request_body(request)
    with write_transaction(db):
        fixed = pin_candidate(db, snapshot)
        original = _admitted_replacement(db, request)
        if original is not None:
            # Redelivery of an already effective request replays its first result and
            # never re-selects a candidate chosen by a later request.
            return original
        previous = select_candidate(db, fixed)
        db.execute(
            'INSERT INTO admitted_replacements VALUES (?, ?, ?)',
            (request.request_id, body, previous),
        )
        return ReplacementResult(request, previous)


def _after_delivery(db, fixed):
    issue, created = issue_if_eligible(db, fixed)
    if issue is not None:
        return 'issued', issue, created
    if is_retired(db, fixed.candidate_id):
        return 'retired', None, False
    if can_issue(db, fixed):
        return 'waiting', None, False
    return 'not_selected', None, False


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
        status, issue, created = _after_delivery(db, fixed)
        if issue is not None and created and before_commit is not None:
            before_commit()
        return DeliveryResult(receipt.receipt_id, status, issue)

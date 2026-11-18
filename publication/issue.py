from publication.eligibility import can_issue
from publication.evidence import load_passing_evidence
from publication.ledger import append_issue, load_issue_for_candidate


def issue_if_eligible(db, snapshot):
    if not db.in_transaction:
        raise RuntimeError('issue_if_eligible requires an active write transaction')
    signed = load_issue_for_candidate(db, snapshot.candidate_id)
    if signed is not None:
        return signed, False
    if not can_issue(db, snapshot):
        return None, False
    receipts = load_passing_evidence(db, snapshot.candidate_id)
    if receipts.keys() != {'zero', 'span'}:
        return None, False
    signed = append_issue(db, snapshot, receipts['zero'].receipt_id, receipts['span'].receipt_id)
    return signed, True

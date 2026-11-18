from dataclasses import asdict, dataclass
import json

from candidate.snapshot import canonical_json, snapshot_digest
from candidate.store import load_candidate
from inspection.span import check_span
from inspection.standards import CheckFinding, CheckStandard, load_check_standard, require_check_kind
from inspection.zero import check_zero
from source.database import station_transaction
from source.registry import require_name
from source.samples import encode_number


@dataclass(frozen=True)
class CheckReceipt:
    receipt_id: str
    candidate_id: str
    input_digest: str
    standard: CheckStandard
    finding: CheckFinding

    def __post_init__(self):
        require_name(self.receipt_id)
        require_name(self.candidate_id)
        require_name(self.input_digest)
        if not isinstance(self.standard, CheckStandard) or not isinstance(self.finding, CheckFinding):
            raise ValueError('receipt requires a check standard and a finding')

    @property
    def kind(self):
        return self.standard.kind

    @property
    def passed(self):
        return self.finding.passed


def evaluate_check(snapshot, standard):
    check = check_zero if standard.kind == 'zero' else check_span
    return check(snapshot, standard)


def encode_check_receipt(receipt):
    payload = asdict(receipt)
    for field in ('reference', 'lower', 'upper'):
        payload['standard'][field] = encode_number(payload['standard'][field])
    payload['finding']['value'] = encode_number(payload['finding']['value'])
    return canonical_json(payload)


def decode_check_receipt(encoded):
    payload = json.loads(encoded)
    payload['standard'] = CheckStandard(**payload['standard'])
    payload['finding'] = CheckFinding(**payload['finding'])
    return CheckReceipt(**payload)


def initialize_check_receipts(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS check_receipts (
            receipt_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
            kind TEXT NOT NULL CHECK(kind IN ('zero', 'span')),
            body TEXT NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0, 1)),
            UNIQUE(candidate_id, kind)
        )
    ''')


def inspect_candidate(db, candidate_id, kind, receipt_id):
    require_check_kind(kind)
    require_name(receipt_id)
    with station_transaction(db):
        snapshot = load_candidate(db, candidate_id)
        claimed = db.execute(
            'SELECT candidate_id, kind FROM check_receipts WHERE receipt_id = ?', (receipt_id,)
        ).fetchone()
        if claimed is not None and tuple(claimed) != (candidate_id, kind):
            raise ValueError(f'conflicting check receipt {receipt_id}')
        original = db.execute(
            'SELECT body FROM check_receipts WHERE candidate_id = ? AND kind = ?', (candidate_id, kind)
        ).fetchone()
        if original is not None:
            return decode_check_receipt(original['body'])
        standard = load_check_standard(db, snapshot.station, kind)
        receipt = CheckReceipt(receipt_id, candidate_id, snapshot_digest(snapshot), standard,
                               evaluate_check(snapshot, standard))
        db.execute(
            'INSERT INTO check_receipts(receipt_id, candidate_id, kind, body) VALUES (?, ?, ?, ?)',
            (receipt_id, candidate_id, kind, encode_check_receipt(receipt)),
        )
    return receipt


def load_check_receipt(db, receipt_id):
    require_name(receipt_id)
    row = db.execute('SELECT body FROM check_receipts WHERE receipt_id = ?', (receipt_id,)).fetchone()
    if row is None:
        raise KeyError(receipt_id)
    return decode_check_receipt(row['body'])


def list_pending_receipts(db):
    return tuple(decode_check_receipt(row['body']) for row in db.execute(
        'SELECT body FROM check_receipts WHERE delivered = 0 ORDER BY receipt_id'
    ))


def confirm_receipt_delivery(db, receipt_id):
    with station_transaction(db):
        changed = db.execute('UPDATE check_receipts SET delivered = 1 WHERE receipt_id = ?', (receipt_id,))
        if changed.rowcount != 1:
            raise KeyError(receipt_id)

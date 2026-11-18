import json

from candidate.snapshot import decode_snapshot, encode_snapshot, snapshot_digest
from inspection.receipts import CheckReceipt, decode_check_receipt, encode_check_receipt, evaluate_check


def initialize_evidence(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS received_candidates (
            candidate_id TEXT PRIMARY KEY,
            snapshot TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS received_evidence (
            receipt_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES received_candidates(candidate_id),
            kind TEXT NOT NULL CHECK(kind IN ('zero', 'span')),
            passed INTEGER NOT NULL CHECK(passed IN (0, 1)),
            body TEXT NOT NULL,
            UNIQUE(candidate_id, kind)
        );
    ''')


def pin_candidate(db, snapshot):
    encoded = encode_snapshot(snapshot)
    fixed = decode_snapshot(encoded)
    db.execute(
        'INSERT INTO received_candidates VALUES (?, ?) ON CONFLICT(candidate_id) DO NOTHING',
        (fixed.candidate_id, encoded),
    )
    existing = db.execute(
        'SELECT snapshot FROM received_candidates WHERE candidate_id = ?', (fixed.candidate_id,)
    ).fetchone()
    if existing['snapshot'] != encoded:
        raise ValueError(f'conflicting received candidate {fixed.candidate_id}')
    return fixed


def load_received_candidate(db, candidate_id):
    row = db.execute(
        'SELECT snapshot FROM received_candidates WHERE candidate_id = ?', (candidate_id,)
    ).fetchone()
    if row is None:
        raise KeyError(candidate_id)
    return decode_snapshot(row['snapshot'])


def record_evidence(db, snapshot, receipt):
    if not isinstance(receipt, CheckReceipt):
        raise ValueError('expected a fixed check receipt')
    if (receipt.candidate_id, receipt.input_digest) != (snapshot.candidate_id, snapshot_digest(snapshot)):
        raise ValueError('check receipt belongs to different fixed inputs')
    if receipt.finding != evaluate_check(snapshot, receipt.standard):
        raise ValueError('check finding differs from the fixed evidence row and standard')
    encoded = encode_check_receipt(receipt)
    db.execute(
        'INSERT INTO received_evidence VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING',
        (receipt.receipt_id, receipt.candidate_id, receipt.kind, int(receipt.passed), encoded),
    )
    row = db.execute('SELECT body FROM received_evidence WHERE receipt_id = ?', (receipt.receipt_id,)).fetchone()
    if row is None or row['body'] != encoded:
        raise ValueError(f'conflicting received evidence {receipt.receipt_id}')


def load_passing_evidence(db, candidate_id):
    fixed = load_received_candidate(db, candidate_id)
    checks = {}
    for row in db.execute(
        'SELECT e.kind, e.body, c.snapshot FROM received_evidence AS e '
        'JOIN received_candidates AS c USING(candidate_id) '
        'LEFT JOIN issues AS i ON i.candidate_id = e.candidate_id '
        'WHERE i.issue_id IS NULL ORDER BY e.candidate_id = ?, e.rowid', (candidate_id,)
    ):
        owner = json.loads(row['snapshot'])
        if (owner['station'], owner['day']) == (fixed.station, fixed.day):
            checks[row['kind']] = decode_check_receipt(row['body'])
    return {kind: receipt for kind, receipt in checks.items() if receipt.passed}

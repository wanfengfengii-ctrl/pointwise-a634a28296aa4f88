from dataclasses import asdict, dataclass
import json

from candidate.snapshot import CandidateSnapshot, canonical_json, decode_snapshot, encode_snapshot, snapshot_digest
from source.database import connect_database, immediate_transaction


@dataclass(frozen=True)
class IssueReceipt:
    issue_id: str
    candidate_id: str
    input_digest: str
    zero_receipt_id: str
    span_receipt_id: str


@dataclass(frozen=True)
class IssueRecord:
    report: CandidateSnapshot
    receipt: IssueReceipt


def open_publication(path):
    return connect_database(path)


write_transaction = immediate_transaction


def initialize_ledger(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS issues (
            issue_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL UNIQUE,
            snapshot TEXT NOT NULL,
            receipt TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS current_issues (
            station TEXT NOT NULL,
            day TEXT NOT NULL,
            issue_id TEXT NOT NULL REFERENCES issues(issue_id),
            PRIMARY KEY(station, day)
        );
    ''')


def issue_number(candidate_id):
    return f'issue:{candidate_id}'


def append_issue(db, snapshot, zero_receipt_id, span_receipt_id):
    if not db.in_transaction:
        raise RuntimeError('append_issue requires an active write transaction')
    receipt = IssueReceipt(issue_number(snapshot.candidate_id), snapshot.candidate_id,
                           snapshot_digest(snapshot), zero_receipt_id, span_receipt_id)
    db.execute(
        'INSERT INTO issues VALUES (?, ?, ?, ?)',
        (receipt.issue_id, snapshot.candidate_id, encode_snapshot(snapshot), canonical_json(asdict(receipt))),
    )
    db.execute(
        'INSERT INTO current_issues VALUES (?, ?, ?) '
        'ON CONFLICT(station, day) DO UPDATE SET issue_id = excluded.issue_id',
        (snapshot.station, snapshot.day, receipt.issue_id),
    )
    return IssueRecord(snapshot, receipt)


def _read_record(row):
    if row is None:
        return None
    return IssueRecord(decode_snapshot(row['snapshot']), IssueReceipt(**json.loads(row['receipt'])))


def load_issue(db, issue_id):
    return _read_record(db.execute(
        'SELECT snapshot, receipt FROM issues WHERE issue_id = ?', (issue_id,)
    ).fetchone())


def load_issue_for_candidate(db, candidate_id):
    return _read_record(db.execute(
        'SELECT snapshot, receipt FROM issues WHERE candidate_id = ?', (candidate_id,)
    ).fetchone())


def load_current_issue(db, station, day):
    return _read_record(db.execute(
        'SELECT issues.snapshot, issues.receipt FROM current_issues '
        'JOIN issues ON issues.issue_id = current_issues.issue_id '
        'WHERE current_issues.station = ? AND current_issues.day = ?', (station, day)
    ).fetchone())

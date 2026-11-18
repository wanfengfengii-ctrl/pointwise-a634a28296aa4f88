from candidate.snapshot import decode_snapshot, encode_snapshot
from source.database import station_transaction
from source.registry import require_name


def initialize_candidate_store(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            revision_id TEXT NOT NULL REFERENCES day_revisions(revision_id),
            snapshot TEXT NOT NULL
        )
    ''')


def save_candidate(db, snapshot):
    encoded = encode_snapshot(snapshot)
    fixed = decode_snapshot(encoded)
    with station_transaction(db):
        revision = db.execute(
            'SELECT station, day, corrects FROM day_revisions WHERE revision_id = ?',
            (fixed.revision_id,),
        ).fetchone()
        if revision is None:
            raise KeyError(fixed.revision_id)
        if tuple(revision) != (fixed.station, fixed.day, fixed.corrects):
            raise ValueError('candidate differs from its revision identity')
        db.execute(
            'INSERT INTO candidates VALUES (?, ?, ?) ON CONFLICT(candidate_id) DO NOTHING',
            (fixed.candidate_id, fixed.revision_id, encoded),
        )
        row = db.execute(
            'SELECT snapshot FROM candidates WHERE candidate_id = ?', (fixed.candidate_id,)
        ).fetchone()
        if row['snapshot'] != encoded:
            raise ValueError(f'conflicting candidate {fixed.candidate_id}')
    return fixed


def load_candidate(db, candidate_id):
    require_name(candidate_id)
    row = db.execute('SELECT snapshot FROM candidates WHERE candidate_id = ?', (candidate_id,)).fetchone()
    if row is None:
        raise KeyError(candidate_id)
    return decode_snapshot(row['snapshot'])

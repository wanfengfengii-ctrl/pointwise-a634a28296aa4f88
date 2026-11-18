from dataclasses import dataclass

from source.database import station_transaction


@dataclass(frozen=True)
class ReplacementRequest:
    request_id: str
    station: str
    day: str
    candidate_id: str
    input_digest: str


@dataclass(frozen=True)
class ReplacementResult:
    request: ReplacementRequest
    previous_candidate_id: str | None


def initialize_replacement_store(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS replacement_requests (
            request_id TEXT PRIMARY KEY,
            station TEXT NOT NULL,
            day TEXT NOT NULL,
            candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
            input_digest TEXT NOT NULL,
            confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0, 1)),
            previous_candidate_id TEXT
        )
    ''')


def load_replacement_request(db, request_id):
    row = db.execute('SELECT * FROM replacement_requests WHERE request_id = ?', (request_id,)).fetchone()
    if row is None:
        raise KeyError(request_id)
    request = ReplacementRequest(row['request_id'], row['station'], row['day'], row['candidate_id'], row['input_digest'])
    result = ReplacementResult(request, row['previous_candidate_id']) if row['confirmed'] else None
    return request, result


def record_pending_request(db, request):
    with station_transaction(db):
        db.execute(
            'INSERT INTO replacement_requests(request_id, station, day, candidate_id, input_digest) '
            'VALUES (?, ?, ?, ?, ?) ON CONFLICT(request_id) DO NOTHING',
            (request.request_id, request.station, request.day, request.candidate_id, request.input_digest),
        )
        original, result = load_replacement_request(db, request.request_id)
        if original != request:
            raise ValueError(f'conflicting replacement request {request.request_id}')
    return result


def record_replacement_result(db, result):
    with station_transaction(db):
        request, original_result = load_replacement_request(db, result.request.request_id)
        if request != result.request or (original_result is not None and original_result != result):
            raise ValueError('replacement result conflicts with the stored request or result')
        if original_result is None:
            db.execute(
                'UPDATE replacement_requests SET confirmed = 1, previous_candidate_id = ? WHERE request_id = ?',
                (result.previous_candidate_id, request.request_id),
            )
    return result

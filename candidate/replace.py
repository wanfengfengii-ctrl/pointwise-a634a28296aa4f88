from candidate.requests import ReplacementRequest, ReplacementResult, record_pending_request, record_replacement_result
from candidate.snapshot import snapshot_digest
from candidate.store import load_candidate
from source.registry import require_name


def replace_candidate(db, station, day, candidate_id, request_id, port):
    require_name(request_id)
    snapshot = load_candidate(db, candidate_id)
    if (station, day) != (snapshot.station, snapshot.day):
        raise ValueError('replacement candidate belongs to a different station day')
    request = ReplacementRequest(request_id, station, day, candidate_id, snapshot_digest(snapshot))
    saved = record_pending_request(db, request)
    if saved is not None:
        return saved
    try:
        result = port(request, snapshot)
    except ConnectionError:
        # Retain the operator's selection when the relay is unavailable.
        previous = db.execute(
            'SELECT candidate_id FROM replacement_requests '
            'WHERE station = ? AND day = ? AND confirmed = 1 ORDER BY rowid DESC LIMIT 1',
            (station, day),
        ).fetchone()
        result = ReplacementResult(request, None if previous is None else previous['candidate_id'])
    if not isinstance(result, ReplacementResult) or result.request != request:
        raise ValueError('replacement port returned a result for different inputs')
    return record_replacement_result(db, result)

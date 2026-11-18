from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from candidate.convert import ConvertedRow, convert_sample
from source.calibrations import CalibrationRevision
from source.registry import require_name
from source.revisions import require_day
from source.samples import RawSample, encode_number, exact_number, optional_number


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(text):
    return sha256(text.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class CandidateSnapshot:
    candidate_id: str
    station: str
    day: str
    revision_id: str
    corrects: str | None
    rows: tuple[ConvertedRow, ...]
    value_digest: str


def comparison_digest(rows):
    return _digest(canonical_json([[row.report_unit, encode_number(row.value)] for row in rows]))


def freeze_snapshot(candidate_id, station, day, revision_id, rows, *, corrects=None):
    require_name(candidate_id)
    require_name(station)
    require_day(day)
    require_name(revision_id)
    if corrects is not None:
        require_name(corrects)
        if corrects == revision_id:
            raise ValueError('revision cannot correct itself')
    frozen = tuple(rows)
    seen = set()
    channels = {}
    calibration_channels = {}
    for position, row in enumerate(frozen):
        require_name(row.sample_id)
        require_name(row.channel)
        require_name(row.calibration_id)
        require_name(row.input_unit)
        require_name(row.report_unit)
        if type(row.position) is not int or row.position != position or row.sample_id in seen:
            raise ValueError('invalid frozen row position or identity')
        seen.add(row.sample_id)
        calibration = CalibrationRevision(
            row.calibration_id, station, row.channel, row.input_unit, row.report_unit,
            exact_number(row.scale), exact_number(row.offset),
        )
        if channels.setdefault(row.channel, calibration) != calibration:
            raise ValueError('frozen rows have inconsistent calibration for a channel')
        if calibration_channels.setdefault(row.calibration_id, row.channel) != row.channel:
            raise ValueError('frozen calibration is referenced by different channels')
        sample = RawSample(position, row.sample_id, row.channel, row.raw)
        if convert_sample(sample, calibration) != row:
            raise ValueError(f'frozen conversion differs for sample {row.sample_id}')
    return CandidateSnapshot(candidate_id, station, day, revision_id, corrects, frozen, comparison_digest(frozen))


def encode_snapshot(snapshot):
    payload = asdict(snapshot)
    rows = payload['rows']
    for row in rows:
        for field in ('raw', 'value', 'scale', 'offset'):
            row[field] = encode_number(row[field])
    return canonical_json(payload)


def decode_snapshot(encoded):
    payload = json.loads(encoded)
    if not isinstance(payload, dict) or not isinstance(payload.get('rows'), list):
        raise ValueError('invalid snapshot object')
    rows = []
    for item in payload['rows']:
        fields = dict(item)
        for field in ('raw', 'value'):
            fields[field] = optional_number(fields[field])
        for field in ('scale', 'offset'):
            fields[field] = exact_number(fields[field])
        rows.append(ConvertedRow(**fields))
    snapshot = freeze_snapshot(
        payload['candidate_id'], payload['station'], payload['day'], payload['revision_id'], rows,
        corrects=payload['corrects'],
    )
    if canonical_json(payload) != encode_snapshot(snapshot):
        raise ValueError('noncanonical or inconsistent frozen candidate')
    return snapshot


def snapshot_digest(snapshot):
    return _digest(encode_snapshot(snapshot))

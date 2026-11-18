from dataclasses import dataclass
from datetime import date

from source.calibrations import CalibrationRevision, load_calibration
from source.database import station_transaction
from source.registry import StationRegistry, require_name
from source.samples import RawSample, encode_number, normalize_samples, optional_number


def require_day(day):
    require_name(day)
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError('station day must use YYYY-MM-DD')
    return day


@dataclass(frozen=True)
class DayRevision:
    revision_id: str
    station: str
    day: str
    corrects: str | None
    samples: tuple[RawSample, ...]
    calibrations: tuple[CalibrationRevision, ...]


def _check_calibration(calibration, station, channel):
    if (calibration.station, calibration.channel) != (station, channel):
        raise ValueError(f'calibration {calibration.calibration_id} belongs to a different channel')
    return calibration


def register_revision(db, revision_id, station, day, samples, calibrations, *, corrects=None):
    require_name(revision_id)
    require_day(day)
    registry = StationRegistry(db)
    with station_transaction(db):
        registry.require_station(station)
        if corrects is not None:
            require_name(corrects)
            predecessor = db.execute(
                'SELECT station, day FROM day_revisions WHERE revision_id = ?', (corrects,)
            ).fetchone()
            if predecessor is None or tuple(predecessor) != (station, day):
                raise ValueError('correction target must be an existing revision of the same station day')
        if db.execute('SELECT 1 FROM day_revisions WHERE revision_id = ?', (revision_id,)).fetchone():
            raise ValueError(f'day revision already exists: {revision_id}')
        rows = normalize_samples(registry, station, samples)
        definitions = {
            channel: _check_calibration(load_calibration(db, calibration_id), station, channel)
            for channel, calibration_id in calibrations.items()
        }
        uncovered = {sample.channel for sample in rows} - definitions.keys()
        if uncovered:
            raise ValueError(f'missing calibration for channels {sorted(uncovered)}')
        db.execute('INSERT INTO day_revisions VALUES (?, ?, ?, ?)', (revision_id, station, day, corrects))
        db.executemany(
            'INSERT INTO revision_calibrations VALUES (?, ?, ?)',
            ((revision_id, cal.channel, cal.calibration_id) for cal in definitions.values()),
        )
        db.executemany(
            'INSERT INTO raw_samples VALUES (?, ?, ?, ?, ?)',
            ((revision_id, sample.position, sample.sample_id, sample.channel, encode_number(sample.raw))
             for sample in rows),
        )
    return revision_id


def load_revision(db, revision_id):
    require_name(revision_id)
    head = db.execute('SELECT * FROM day_revisions WHERE revision_id = ?', (revision_id,)).fetchone()
    if head is None:
        raise KeyError(revision_id)
    calibrations = tuple(
        _check_calibration(load_calibration(db, row['calibration_id']), head['station'], row['channel'])
        for row in db.execute(
            'SELECT channel, calibration_id FROM revision_calibrations '
            'WHERE revision_id = ? ORDER BY channel', (revision_id,)
        )
    )
    samples = tuple(
        RawSample(row['position'], row['sample_id'], row['channel'], optional_number(row['raw']))
        for row in db.execute(
            'SELECT * FROM raw_samples WHERE revision_id = ? ORDER BY position', (revision_id,)
        )
    )
    return DayRevision(revision_id, head['station'], head['day'], head['corrects'], samples, calibrations)

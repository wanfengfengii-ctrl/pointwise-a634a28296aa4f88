from dataclasses import dataclass
from fractions import Fraction

from source.database import station_transaction
from source.registry import StationRegistry, require_name
from source.samples import exact_number


@dataclass(frozen=True)
class CalibrationRevision:
    calibration_id: str
    station: str
    channel: str
    input_unit: str
    report_unit: str
    scale: Fraction
    offset: Fraction


def register_calibration(db, station, channel, calibration_id, scale, offset, *, only_missing=False):
    require_name(calibration_id)
    scale = exact_number(scale)
    offset = exact_number(offset)
    with station_transaction(db):
        definition = StationRegistry(db).require_channel(station, channel)
        wanted = CalibrationRevision(
            calibration_id, station, channel, definition.input_unit, definition.report_unit,
            scale, offset,
        )
        db.execute(
            'INSERT INTO calibrations VALUES (?, ?, ?, ?, ?, ?, ?) '
            'ON CONFLICT(calibration_id) DO NOTHING',
            (calibration_id, station, channel, wanted.input_unit, wanted.report_unit,
             str(scale), str(offset)),
        )
        actual = load_calibration(db, calibration_id)
        if actual != wanted and (not only_missing or (actual.station, actual.channel) != (station, channel)):
            raise ValueError(f'conflicting calibration {calibration_id}')
    return actual


def load_calibration(db, calibration_id):
    require_name(calibration_id)
    row = db.execute(
        'SELECT * FROM calibrations WHERE calibration_id = ?', (calibration_id,)
    ).fetchone()
    if row is None:
        raise KeyError(calibration_id)
    channel = StationRegistry(db).require_channel(row['station'], row['channel'])
    if (row['input_unit'], row['report_unit']) != (channel.input_unit, channel.report_unit):
        raise ValueError(f'invalid calibration units for {calibration_id}')
    return CalibrationRevision(
        calibration_id, channel.station, channel.channel, channel.input_unit, channel.report_unit,
        exact_number(row['scale']), exact_number(row['offset']),
    )

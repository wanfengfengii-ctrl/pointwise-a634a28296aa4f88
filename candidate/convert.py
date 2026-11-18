from dataclasses import dataclass
from fractions import Fraction

from source.calibrations import CalibrationRevision
from source.samples import RawSample, exact_number, optional_number


@dataclass(frozen=True)
class ConvertedRow:
    position: int
    sample_id: str
    channel: str
    raw: Fraction | None
    value: Fraction | None
    calibration_id: str
    input_unit: str
    report_unit: str
    scale: Fraction
    offset: Fraction


def convert_sample(sample: RawSample, calibration: CalibrationRevision):
    if sample.channel != calibration.channel:
        raise ValueError('sample and calibration channels differ')
    scale = exact_number(calibration.scale)
    offset = exact_number(calibration.offset)
    raw = optional_number(sample.raw)
    value = None if raw is None else scale * raw + offset
    return ConvertedRow(
        sample.position, sample.sample_id, sample.channel, raw, value,
        calibration.calibration_id, calibration.input_unit, calibration.report_unit, scale, offset,
    )

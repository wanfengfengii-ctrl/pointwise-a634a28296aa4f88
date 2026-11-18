from dataclasses import dataclass
from fractions import Fraction

from source.registry import require_name


def exact_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, Fraction)):
        raise ValueError('expected an integer, a fraction string or a Fraction')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f'invalid exact number {value!r}') from exc


def optional_number(value):
    return None if value is None else exact_number(value)


def encode_number(value):
    return None if value is None else str(exact_number(value))


@dataclass(frozen=True)
class RawSample:
    position: int
    sample_id: str
    channel: str
    raw: Fraction | None


def normalize_samples(registry, station, samples):
    rows = []
    seen = set()
    known_channels = set()
    for position, (sample_id, channel, raw) in enumerate(samples):
        require_name(sample_id)
        require_name(channel)
        if sample_id in seen:
            raise ValueError(f'duplicate sample {sample_id}')
        if channel not in known_channels:
            registry.require_channel(station, channel)
            known_channels.add(channel)
        rows.append(RawSample(position, sample_id, channel, optional_number(raw)))
        seen.add(sample_id)
    return tuple(rows)

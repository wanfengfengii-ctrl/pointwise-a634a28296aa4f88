from dataclasses import dataclass
from fractions import Fraction

from source.database import station_transaction
from source.registry import StationRegistry, require_name
from source.samples import exact_number, optional_number


def require_check_kind(kind):
    if kind not in ('zero', 'span'):
        raise ValueError(f'unknown check kind {kind!r}')
    return kind


@dataclass(frozen=True)
class CheckStandard:
    kind: str
    channel: str
    sample_id: str
    report_unit: str
    reference: Fraction
    lower: Fraction
    upper: Fraction

    def __post_init__(self):
        require_check_kind(self.kind)
        for value in (self.channel, self.sample_id, self.report_unit):
            require_name(value)
        for field in ('reference', 'lower', 'upper'):
            object.__setattr__(self, field, exact_number(getattr(self, field)))
        if not within_closed_interval(self.reference, self.lower, self.upper):
            raise ValueError('check reference must lie in the closed interval')
        if self.kind == 'zero' and self.reference != 0:
            raise ValueError('zero check must use a zero reference')


@dataclass(frozen=True)
class CheckFinding:
    position: int | None
    value: Fraction | None
    passed: bool
    reason: str

    def __post_init__(self):
        if self.position is not None and (type(self.position) is not int or self.position < 0):
            raise ValueError('invalid evidence position')
        if type(self.passed) is not bool:
            raise ValueError('invalid check verdict')
        object.__setattr__(self, 'value', optional_number(self.value))
        require_name(self.reason)


def initialize_check_standards(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS check_standards (
            station TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('zero', 'span')),
            channel TEXT NOT NULL,
            sample_id TEXT NOT NULL,
            report_unit TEXT NOT NULL,
            reference TEXT NOT NULL,
            lower TEXT NOT NULL,
            upper TEXT NOT NULL,
            PRIMARY KEY(station, kind),
            FOREIGN KEY(station, channel) REFERENCES channels(station, channel)
        )
    ''')


def _store_standard(db, station, standard, only_missing):
    channel = StationRegistry(db).require_channel(station, standard.channel)
    if channel.report_unit != standard.report_unit:
        raise ValueError('check unit differs from channel report unit')
    conflict = 'DO NOTHING' if only_missing else (
        'DO UPDATE SET channel=excluded.channel, sample_id=excluded.sample_id, '
        'report_unit=excluded.report_unit, reference=excluded.reference, '
        'lower=excluded.lower, upper=excluded.upper'
    )
    db.execute(
        'INSERT INTO check_standards VALUES (?, ?, ?, ?, ?, ?, ?, ?) '
        f'ON CONFLICT(station, kind) {conflict}',
        (station, standard.kind, standard.channel, standard.sample_id, standard.report_unit,
         str(standard.reference), str(standard.lower), str(standard.upper)),
    )


def register_check_standard(db, station, standard):
    with station_transaction(db):
        _store_standard(db, station, standard, False)


def seed_check_standards(db, station, channel, report_unit):
    standards = (
        CheckStandard('zero', channel, 'zero-trial', report_unit, 0, '-1/4', '1/4'),
        CheckStandard('span', channel, 'span-trial', report_unit, '7/4', '3/2', 2),
    )
    with station_transaction(db):
        for standard in standards:
            _store_standard(db, station, standard, True)


def load_check_standard(db, station, kind):
    require_check_kind(kind)
    row = db.execute(
        'SELECT kind, channel, sample_id, report_unit, reference, lower, upper '
        'FROM check_standards WHERE station = ? AND kind = ?', (station, kind)
    ).fetchone()
    if row is None:
        raise KeyError((station, kind))
    return CheckStandard(**dict(row))


def locate_evidence(snapshot, standard):
    return next((row for row in snapshot.rows
                 if (row.channel, row.sample_id) == (standard.channel, standard.sample_id)), None)


def unavailable_evidence(row, standard):
    if row is None:
        return CheckFinding(None, None, False, 'missing_sample')
    if row.value is None:
        return CheckFinding(row.position, None, False, 'missing_value')
    if row.report_unit != standard.report_unit:
        return CheckFinding(row.position, row.value, False, 'wrong_unit')
    return None


def within_closed_interval(value, lower, upper):
    return lower <= value <= upper

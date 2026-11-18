from dataclasses import dataclass

from source.database import station_transaction


def require_name(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('expected a nonempty identifier without surrounding whitespace')
    return value


@dataclass(frozen=True)
class Channel:
    station: str
    channel: str
    input_unit: str
    report_unit: str


class StationRegistry:
    def __init__(self, db):
        self.db = db

    def register_station(self, station, name, *, only_missing=False):
        require_name(station)
        require_name(name)
        with station_transaction(self.db):
            self.db.execute(
                'INSERT INTO stations VALUES (?, ?) ON CONFLICT(station) DO NOTHING',
                (station, name),
            )
            actual = self.db.execute(
                'SELECT name FROM stations WHERE station = ?', (station,)
            ).fetchone()['name']
            if not only_missing and actual != name:
                raise ValueError(f'conflicting station definition {station}')
        return actual

    def require_station(self, station):
        require_name(station)
        row = self.db.execute(
            'SELECT name FROM stations WHERE station = ?', (station,)
        ).fetchone()
        if row is None:
            raise KeyError(station)
        return row['name']

    def register_channel(self, station, channel, input_unit, report_unit, *, only_missing=False):
        definition = Channel(*(require_name(value) for value in (
            station, channel, input_unit, report_unit
        )))
        with station_transaction(self.db):
            self.require_station(station)
            self.db.execute(
                'INSERT INTO channels VALUES (?, ?, ?, ?) '
                'ON CONFLICT(station, channel) DO NOTHING',
                (station, channel, input_unit, report_unit),
            )
            actual = self.require_channel(station, channel)
            if not only_missing and actual != definition:
                raise ValueError(f'conflicting channel definition {station}/{channel}')
        return actual

    def require_channel(self, station, channel):
        require_name(station)
        require_name(channel)
        row = self.db.execute(
            'SELECT station, channel, input_unit, report_unit FROM channels '
            'WHERE station = ? AND channel = ?', (station, channel)
        ).fetchone()
        if row is None:
            raise KeyError((station, channel))
        return Channel(**dict(row))

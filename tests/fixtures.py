from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from candidate.assemble import prepare_candidate
from candidate.replace import replace_candidate
from demo import CHANNEL, DAY, STATION, initialize_source, seed_demo, trial_samples
from inspection.delivery import redeliver_receipt
from inspection.receipts import inspect_candidate
from publication.admission import admit_replacement, deliver_receipt, initialize_publication
from publication.ledger import open_publication
from receipt.lookup import read_report
from source.database import open_station
from source.revisions import register_revision


class LostReply(Exception):
    pass


def lose_reply(port):
    def run(*args):
        result = port(*args)
        raise LostReply(result)
    return run


class StationCase(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix='quay-tests-')
        self.addCleanup(folder.cleanup)
        self.station_path = Path(folder.name) / 'station.sqlite'
        self.publication_path = Path(folder.name) / 'publication.sqlite'
        self.station = self.publication = None
        self.addCleanup(self.close_stores)
        self.reopen()
        seed_demo(self.station)

    def close_station(self):
        if self.station is not None:
            self.station.close()
            self.station = None

    def close_stores(self):
        self.close_station()
        if self.publication is not None:
            self.publication.close()
            self.publication = None

    def reopen(self):
        self.close_stores()
        self.station = open_station(self.station_path)
        self.publication = open_publication(self.publication_path)
        initialize_source(self.station)
        initialize_publication(self.publication)

    def prepare(self, name, *, calibration='C1', span=3, samples=None, corrects=None):
        if samples is None:
            samples = trial_samples(span)
        revision_id = 'day-' + name
        register_revision(self.station, revision_id, STATION, DAY, samples, {CHANNEL: calibration},
                          corrects=corrects)
        return prepare_candidate(self.station, revision_id, name)

    def select(self, name, *, request_id=None, port=None):
        if port is None:
            port = partial(admit_replacement, self.publication)
        return replace_candidate(self.station, STATION, DAY, name, request_id or 'select-' + name, port)

    def inspect(self, name, kind):
        return inspect_candidate(self.station, name, kind, f'{name}-{kind}')

    def send(self, name, kind, *, port=None):
        if port is None:
            port = partial(deliver_receipt, self.publication)
        return redeliver_receipt(self.station, f'{name}-{kind}', port)

    def sign(self, name):
        self.inspect(name, 'zero')
        self.inspect(name, 'span')
        self.send(name, 'zero')
        return self.send(name, 'span').issue

    def current(self):
        return read_report(self.publication, station=STATION, day=DAY)

    def history(self, name):
        return read_report(self.publication, issue_id='issue:' + name)

    def issue_count(self):
        return self.publication.execute('SELECT count(*) FROM issues').fetchone()[0]

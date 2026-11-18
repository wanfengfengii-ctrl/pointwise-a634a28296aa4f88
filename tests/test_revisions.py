from fractions import Fraction

from candidate.assemble import prepare_candidate
from candidate.store import load_candidate
from demo import CHANNEL, DAY, STATION, trial_samples
from source.calibrations import register_calibration
from source.revisions import load_revision, register_revision
from tests.fixtures import StationCase


class RevisionTests(StationCase):
    def test_unknown_calibration_rejects(self):
        self.prepare('R0')
        original = load_revision(self.station, 'day-R0')
        with self.assertRaises(KeyError):
            register_revision(self.station, 'bad', STATION, DAY, trial_samples(),
                              {CHANNEL: 'absent'}, corrects='day-R0')
        self.assertEqual(load_revision(self.station, 'day-R0'), original)
        with self.assertRaises(KeyError):
            load_revision(self.station, 'bad')
        with self.assertRaises(KeyError):
            prepare_candidate(self.station, 'bad', 'unborn')
        with self.assertRaises(KeyError):
            load_candidate(self.station, 'unborn')

    def test_invalid_target(self):
        self.prepare('R0')
        original = load_revision(self.station, 'day-R0')
        register_revision(self.station, 'another-day', STATION, '2026-10-13', trial_samples(), {CHANNEL: 'C1'})
        for previous in ('nonexistent', 'another-day'):
            with self.subTest(previous=previous), self.assertRaises(ValueError):
                register_revision(self.station, 'bad', STATION, DAY, trial_samples(), {CHANNEL: 'C3'},
                                  corrects=previous)
        with self.assertRaises(KeyError):
            load_revision(self.station, 'bad')
        self.assertEqual(load_revision(self.station, 'day-R0'), original)

    def test_successor_keeps_original(self):
        old = self.prepare('R0')
        original = load_revision(self.station, 'day-R0')
        new = self.prepare('R1', calibration='C3', corrects='day-R0')
        self.assertEqual(load_revision(self.station, 'day-R0'), original)
        self.assertEqual(load_revision(self.station, 'day-R1').corrects, 'day-R0')
        self.assertEqual(load_candidate(self.station, 'R0'), old)
        self.assertEqual((old.rows[0].calibration_id, old.rows[0].value), ('C1', Fraction(7, 4)))
        self.assertEqual((new.rows[0].calibration_id, new.rows[0].value), ('C3', Fraction(3, 2)))
        with self.assertRaises(ValueError):
            register_calibration(self.station, STATION, CHANNEL, 'C1', '1/2', '1/0')
        with self.assertRaises(ValueError):
            register_calibration(self.station, STATION, CHANNEL, 'C1', '1/3', 0)
        self.assertEqual(load_revision(self.station, 'day-R0'), original)

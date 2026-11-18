from contextlib import contextmanager
import sqlite3


def connect_database(path):
    db = sqlite3.connect(path, isolation_level=None, timeout=10)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        return db
    except BaseException:
        db.close()
        raise


def open_station(path):
    return connect_database(path)


@contextmanager
def immediate_transaction(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise


station_transaction = immediate_transaction


def initialize_station(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS stations (
            station TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS channels (
            station TEXT NOT NULL REFERENCES stations(station),
            channel TEXT NOT NULL,
            input_unit TEXT NOT NULL,
            report_unit TEXT NOT NULL,
            PRIMARY KEY(station, channel)
        );
        CREATE TABLE IF NOT EXISTS calibrations (
            calibration_id TEXT PRIMARY KEY,
            station TEXT NOT NULL,
            channel TEXT NOT NULL,
            input_unit TEXT NOT NULL,
            report_unit TEXT NOT NULL,
            scale TEXT NOT NULL,
            offset TEXT NOT NULL,
            FOREIGN KEY(station, channel) REFERENCES channels(station, channel)
        );
        CREATE TABLE IF NOT EXISTS day_revisions (
            revision_id TEXT PRIMARY KEY,
            station TEXT NOT NULL REFERENCES stations(station),
            day TEXT NOT NULL,
            corrects TEXT REFERENCES day_revisions(revision_id)
        );
        CREATE TABLE IF NOT EXISTS revision_calibrations (
            revision_id TEXT NOT NULL REFERENCES day_revisions(revision_id),
            channel TEXT NOT NULL,
            calibration_id TEXT NOT NULL REFERENCES calibrations(calibration_id),
            PRIMARY KEY(revision_id, channel)
        );
        CREATE TABLE IF NOT EXISTS raw_samples (
            revision_id TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0),
            sample_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            raw TEXT,
            PRIMARY KEY(revision_id, position),
            UNIQUE(revision_id, sample_id),
            FOREIGN KEY(revision_id, channel)
                REFERENCES revision_calibrations(revision_id, channel)
        );
    ''')

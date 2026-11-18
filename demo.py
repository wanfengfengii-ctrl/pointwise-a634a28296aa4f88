from contextlib import closing
from functools import partial
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from candidate.assemble import prepare_candidate
from candidate.replace import replace_candidate
from candidate.requests import initialize_replacement_store
from candidate.store import initialize_candidate_store
from inspection.delivery import redeliver_receipt
from inspection.receipts import initialize_check_receipts, inspect_candidate
from inspection.standards import initialize_check_standards, seed_check_standards
from publication.admission import admit_replacement, deliver_receipt, initialize_publication
from publication.ledger import open_publication
from receipt.lookup import read_report
from receipt.package import export_report
from receipt.verify import verify_package
from source.calibrations import register_calibration
from source.database import initialize_station, open_station
from source.registry import StationRegistry
from source.revisions import register_revision


STATION = 'QC-07'
DAY = '2026-10-14'
CHANNEL = 'displacement'


def initialize_source(db):
    initialize_station(db)
    initialize_candidate_store(db)
    initialize_replacement_store(db)
    initialize_check_standards(db)
    initialize_check_receipts(db)


def seed_demo(db):
    registry = StationRegistry(db)
    registry.register_station(STATION, '岸桥检测站', only_missing=True)
    channel = registry.register_channel(STATION, CHANNEL, 'mV', 'mm', only_missing=True)
    for calibration_id, offset in (('C1', '1/4'), ('C2', '1/4'), ('C3', '0')):
        register_calibration(db, STATION, CHANNEL, calibration_id, '1/2', offset, only_missing=True)
    seed_check_standards(db, STATION, CHANNEL, channel.report_unit)


def trial_samples(span=3):
    return [('reading', CHANNEL, 3), ('zero-trial', CHANNEL, 0), ('gap', CHANNEL, None),
            ('mid', CHANNEL, 2), ('span-trial', CHANNEL, span), ('repeat', CHANNEL, 3)]


def run_demo():
    with TemporaryDirectory(prefix='quay-handover-') as directory:
        root = Path(directory)
        with closing(open_publication(root / 'publication.sqlite')) as publication:
            initialize_publication(publication)
            with closing(open_station(root / 'station.sqlite')) as station:
                initialize_source(station)
                seed_demo(station)
                for number, calibration in enumerate(('C1', 'C1', 'C2')):
                    previous = f'D{number - 1}' if number else None
                    register_revision(station, f'D{number}', STATION, DAY, trial_samples(),
                                      {CHANNEL: calibration}, corrects=previous)
                    prepare_candidate(station, f'D{number}', f'R{number}')
                    for kind in ('zero', 'span'):
                        inspect_candidate(station, f'R{number}', kind, f'R{number}-{kind}')
                send = partial(redeliver_receipt, station, port=partial(deliver_receipt, publication))
                select = partial(replace_candidate, station, STATION, DAY,
                                 port=partial(admit_replacement, publication))
                send('R0-span')
                initial = send('R0-zero').issue
                select('R1', 'select-R1')
                send('R1-zero')
                select('R2', 'select-R2')
                retired = send('R1-span')
                incomplete = send('R2-zero')
                interim = read_report(publication, station=STATION, day=DAY)
                if retired.status != 'retired' or incomplete.status != 'waiting' or interim != initial:
                    raise RuntimeError('DAILY_REPORT_WRONG_REVISION')
                signed = send('R2-span').issue
                if signed is None or send('R2-span').issue != signed:
                    raise RuntimeError('R2 issue did not converge')
            current = read_report(publication, station=STATION, day=DAY)
            history = read_report(publication, issue_id='issue:R0')
            package = export_report(publication, 'issue:R2')
            actual = [current.receipt.issue_id, history.receipt.issue_id, verify_package(package)]
            expected = ['issue:R2', 'issue:R0', True]
            expected_values = ['7/4', '1/4', None]
            actual_values = [None if row.value is None else str(row.value) for row in current.report.rows[:3]]
            if actual != expected or actual_values != expected_values:
                raise RuntimeError('unexpected handover values or provenance')
            evidence = {
                'case_id': 'late_receipts',
                'input': {'station': STATION, 'day': DAY, 'order': ['R1-zero', 'select-R2', 'R1-span', 'R2-zero', 'R2-span']},
                'expected': ['retired', 'waiting', 'issue:R0'],
                'actual': [retired.status, incomplete.status, interim.receipt.issue_id],
                'downstream_expected': {'issues_and_package': expected, 'first_values': expected_values},
                'downstream_actual': {'issues_and_package': actual, 'first_values': actual_values},
                'code_paths': ['candidate/replace.py', 'publication/admission.py', 'publication/issue.py', 'receipt/lookup.py', 'receipt/verify.py'],
                'oracle': 'R2 only becomes current after both R2 checks. Manually applying 1/2 × raw + 1/4 to 3 and 0 gives 7/4 and 1/4. Missing stays missing.',
            }
            print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    run_demo()

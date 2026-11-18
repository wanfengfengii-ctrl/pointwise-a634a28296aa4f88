from functools import partial
import json

from candidate.snapshot import snapshot_digest
from publication.admission import deliver_receipt
from receipt.package import export_report
from receipt.verify import verify_package
from tests.fixtures import StationCase


MARKER = 'DAILY_REPORT_WRONG_REVISION'


def receipt_tuple(issue):
    if issue is None:
        return None
    receipt = issue.receipt
    return [receipt.issue_id, receipt.zero_receipt_id, receipt.span_receipt_id]


def read_ledger(case):
    return {
        'current': receipt_tuple(case.current()),
        'R0': receipt_tuple(case.history('R0')),
        'R1': receipt_tuple(case.history('R1')),
        'R2': receipt_tuple(case.history('R2')),
        'issues': case.issue_count(),
    }


def compare(failures, observation, expected, actual):
    if expected != actual:
        failures.append({'observation': observation, 'expected': expected, 'actual': actual})


def prepare(case):
    case.sign(case.prepare('R0').candidate_id)
    old = case.prepare('R1', corrects='day-R0')
    new = case.prepare('R2', calibration='C2', corrects='day-R1')
    if old.value_digest != new.value_digest or snapshot_digest(old) == snapshot_digest(new):
        raise AssertionError('incident requires two equal-value, distinct fixed candidates')
    case.select('R1')
    for candidate in ('R1', 'R2'):
        for kind in ('zero', 'span'):
            if not case.inspect(candidate, kind).passed:
                raise AssertionError('incident fixture requires passing trial values')


def mixed_checks(case, failures):
    accepted = case.select('R2')
    case.send('R1', 'span')
    case.send('R2', 'zero')
    compare(failures, 'mixed_checks', PRIOR_ONLY, read_ledger(case))
    compare(failures, 'replacement_predecessor', 'R1', accepted.previous_candidate_id)
    case.send('R2', 'span')
    case.reopen()
    for candidate, kind in (('R2', 'span'), ('R2', 'zero'), ('R1', 'zero'), ('R1', 'span')):
        case.send(candidate, kind)
    case.close_station()
    compare(failures, 'after_both_new_checks', NEW_SIGNED, read_ledger(case))
    if case.history('R2') is not None:
        compare(failures, 'offline_export', True, verify_package(export_report(case.publication, 'issue:R2')))


def old_issue_after_replacement(case, failures):
    case.send('R1', 'zero')

    def replace_before_decision():
        case.select('R2')

    port = partial(deliver_receipt, case.publication, before_decision=replace_before_decision)
    case.send('R1', 'span', port=port)
    compare(failures, 'old_issue_after_replacement', PRIOR_ONLY, read_ledger(case))


def undelivered_replacement(case, failures):
    case.send('R1', 'zero')

    def fail_before_delivery(request, snapshot):
        raise ConnectionError('simulated unavailable relay before delivering the request')

    try:
        result = case.select('R2', port=fail_before_delivery)
    except ConnectionError:
        case.reopen()
        result = case.select('R2')
        compare(failures, 'retried_predecessor', 'R1', result.previous_candidate_id)
        case.send('R1', 'span')
        compare(failures, 'old_issue_after_retry', PRIOR_ONLY, read_ledger(case))
    else:
        case.send('R1', 'span')
        compare(failures, 'success_before_delivery', None, result.request.request_id)
        compare(failures, 'old_issue_after_false_success', PRIOR_ONLY, read_ledger(case))


PRIOR = ['issue:R0', 'R0-zero', 'R0-span']
NEW = ['issue:R2', 'R2-zero', 'R2-span']
PRIOR_ONLY = {'current': PRIOR, 'R0': PRIOR, 'R1': None, 'R2': None, 'issues': 1}
NEW_SIGNED = {'current': NEW, 'R0': PRIOR, 'R1': None, 'R2': NEW, 'issues': 2}


def main():
    failures = []
    for scenario in (mixed_checks, old_issue_after_replacement, undelivered_replacement):
        case = StationCase()
        try:
            case.setUp()
            prepare(case)
            scenario(case, failures)
        finally:
            case.doCleanups()
    if failures:
        print(MARKER, json.dumps(failures, sort_keys=True))
        return 1
    print(json.dumps({'after_mixed_checks': PRIOR_ONLY, 'after_both_new_checks': NEW_SIGNED,
                      'after_old_late_check': PRIOR_ONLY, 'after_retried_replacement': PRIOR_ONLY}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

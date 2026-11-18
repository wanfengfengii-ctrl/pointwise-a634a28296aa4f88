from publication.ledger import load_current_issue, load_issue
from source.registry import require_name
from source.revisions import require_day


def read_report(db, *, station=None, day=None, issue_id=None):
    if issue_id is not None:
        if station is not None or day is not None:
            raise ValueError('choose a station day or a single issue number')
        return load_issue(db, require_name(issue_id))
    if station is None or day is None:
        raise ValueError('station and day are both required for current lookup')
    return load_current_issue(db, require_name(station), require_day(day))

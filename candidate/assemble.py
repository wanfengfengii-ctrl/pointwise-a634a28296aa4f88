from candidate.convert import convert_sample
from candidate.snapshot import freeze_snapshot
from candidate.store import save_candidate
from source.revisions import load_revision


def prepare_candidate(db, revision_id, candidate_id):
    revision = load_revision(db, revision_id)
    by_channel = {calibration.channel: calibration for calibration in revision.calibrations}
    rows = (convert_sample(sample, by_channel[sample.channel]) for sample in revision.samples)
    snapshot = freeze_snapshot(
        candidate_id, revision.station, revision.day, revision_id, rows, corrects=revision.corrects,
    )
    return save_candidate(db, snapshot)

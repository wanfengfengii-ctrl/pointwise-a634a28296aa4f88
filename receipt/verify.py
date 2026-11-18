from candidate.snapshot import decode_snapshot, freeze_snapshot, snapshot_digest
from publication.ledger import IssueReceipt, issue_number
from receipt.manifest import encode_manifest, package_digest
from source.registry import require_name


def verify_provenance(snapshot):
    try:
        checked = freeze_snapshot(
            snapshot.candidate_id, snapshot.station, snapshot.day, snapshot.revision_id, snapshot.rows,
            corrects=snapshot.corrects,
        )
        return checked == snapshot
    except (AttributeError, TypeError, ValueError):
        return False


def verify_package(package):
    try:
        if not isinstance(package, dict) or set(package) != {'manifest', 'digest'}:
            return False
        manifest = package['manifest']
        if not isinstance(manifest, dict) or set(manifest) != {'version', 'report', 'receipt'}:
            return False
        if type(manifest['version']) is not int or manifest['version'] != 1:
            return False
        if package_digest(manifest) != package['digest']:
            return False
        report = decode_snapshot(encode_manifest(manifest['report']))
        receipt = IssueReceipt(**manifest['receipt'])
        evidence_ids = (require_name(receipt.zero_receipt_id), require_name(receipt.span_receipt_id))
        return (receipt.issue_id == issue_number(report.candidate_id)
                and receipt.candidate_id == report.candidate_id
                and receipt.input_digest == snapshot_digest(report)
                and evidence_ids[0] != evidence_ids[1]
                and verify_provenance(report))
    except (KeyError, TypeError, ValueError):
        return False

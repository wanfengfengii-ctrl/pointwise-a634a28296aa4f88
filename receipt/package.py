from receipt.lookup import read_report
from receipt.manifest import build_manifest, package_digest


def build_package(issue):
    manifest = build_manifest(issue)
    return {'manifest': manifest, 'digest': package_digest(manifest)}


def export_report(db, issue_id):
    issue = read_report(db, issue_id=issue_id)
    if issue is None:
        raise KeyError(issue_id)
    return build_package(issue)

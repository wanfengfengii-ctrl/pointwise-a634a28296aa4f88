from dataclasses import asdict
from hashlib import sha256
import json

from candidate.snapshot import canonical_json, encode_snapshot


def build_manifest(issue):
    return {'version': 1, 'report': json.loads(encode_snapshot(issue.report)), 'receipt': asdict(issue.receipt)}


def encode_manifest(manifest):
    return canonical_json(manifest)


def package_digest(manifest):
    return sha256(encode_manifest(manifest).encode('utf-8')).hexdigest()

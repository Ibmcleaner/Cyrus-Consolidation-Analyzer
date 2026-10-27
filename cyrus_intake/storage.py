"""Immutable Cloud Storage writer for staged intake evidence."""

from __future__ import annotations

import json
from typing import Mapping

from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage


def store_stage(bucket_name: str, bundle: dict, raw_sources: Mapping[str, bytes]) -> dict:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    prefix = f"season={bundle['season']}/week={int(bundle['week']):02d}"
    created, existing = [], []

    for source in bundle["sources"]:
        kind = source["kind"]
        digest = source["sha256"]
        name = f"{prefix}/raw/{kind}-{digest}.pdf"
        _create_only(bucket, name, raw_sources[kind], "application/pdf", created, existing)

    bundle_name = f"{prefix}/bundles/{bundle['bundleSha256']}.json"
    payload = json.dumps(bundle, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
    _create_only(bucket, bundle_name, payload, "application/json; charset=utf-8", created, existing)
    return {"bucket": bucket_name, "created": created, "alreadyExisted": existing, "bundleObject": bundle_name}


def _create_only(bucket, name: str, data: bytes, content_type: str, created: list, existing: list) -> None:
    blob = bucket.blob(name)
    try:
        blob.upload_from_string(data, content_type=content_type, if_generation_match=0)
        created.append(name)
    except PreconditionFailed:
        existing.append(name)

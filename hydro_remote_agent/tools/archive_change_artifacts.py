from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ROLE_SUFFIX = {
    "change_mask": ".png",
    "change_probability_map": ".npz",
    "change_regions": ".json",
    "change_manifest": ".json",
    "quality_report": ".json",
    "diagnostic_overlay": ".png",
    "quality_manifest": ".json",
}


def artifact_id(artifact_uri: str) -> str:
    return artifact_uri[len("artifact://") :] if artifact_uri.startswith("artifact://") else artifact_uri


def download(base_url: str, artifact_uri: str, target: Path, timeout: float, asset_base_url: str | None) -> dict[str, Any]:
    artifact_key = artifact_id(artifact_uri)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/v1/assets/{artifact_key}/download", timeout=timeout) as response:
            payload = json.loads(response.read().decode())
        url = payload.get("download_url")
        if not url:
            raise RuntimeError("download_url missing")
        request: str | urllib.request.Request = url
        if asset_base_url:
            original = urlsplit(url)
            tunnel = urlsplit(asset_base_url)
            rewritten = urlunsplit((tunnel.scheme, tunnel.netloc, original.path, original.query, original.fragment))
            request = urllib.request.Request(rewritten, headers={"Host": original.netloc})
        hasher = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as handle:
            while True:
                chunk = response.read(8 * 1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                hasher.update(chunk)
        digest = hasher.hexdigest()
        return {"status": "downloaded", "artifact_uri": artifact_uri, "path": str(target), "sha256": digest, "bytes": target.stat().st_size}
    except Exception as exc:
        return {"status": "failed", "artifact_uri": artifact_uri, "path": str(target), "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive change-detection artifacts; safe to resume after network recovery.")
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:28080")
    parser.add_argument("--asset-base-url")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--include-report", action="append")
    parser.add_argument("--role", action="append", choices=sorted(ROLE_SUFFIX))
    args = parser.parse_args()
    records: list[dict[str, Any]] = []
    files = sorted(path for path in args.reports_dir.glob("REAL_CHANGE_*.json") if ".progress." not in path.name)
    if args.include_report:
        include = set(args.include_report)
        files = [path for path in files if path.name in include]
    for report_path in files:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        pairs = report.get("pairs")
        if pairs is None and report.get("steps"):
            pairs = [{"pair_id": report.get("run_id", "canary"), "change": report["steps"][0], "verification": report["steps"][1]}]
        for pair in pairs or []:
            pair_id = pair.get("pair_id", "unknown")
            for role, uri in {
                "change_mask": pair.get("change", {}).get("result", {}).get("artifacts", {}).get("change_mask"),
                "change_probability_map": pair.get("change", {}).get("result", {}).get("artifacts", {}).get("change_probability_map"),
                "change_regions": pair.get("change", {}).get("result", {}).get("artifacts", {}).get("change_regions"),
                "change_manifest": pair.get("change", {}).get("result", {}).get("manifest_path"),
                "quality_report": pair.get("verification", {}).get("result", {}).get("artifacts", {}).get("quality_report"),
                "diagnostic_overlay": pair.get("verification", {}).get("result", {}).get("artifacts", {}).get("diagnostic_overlay"),
                "quality_manifest": pair.get("verification", {}).get("result", {}).get("manifest_path"),
            }.items():
                if args.role and role not in args.role:
                    continue
                if not isinstance(uri, str) or not uri.startswith("artifact://"):
                    continue
                target = args.output_dir / pair_id / f"{role}_{artifact_id(uri)}{ROLE_SUFFIX[role]}"
                records.append({"status": "pending", "artifact_uri": uri, "path": str(target)} if args.inventory_only else download(args.base_url, uri, target, args.timeout, args.asset_base_url))
    summary = {"schema_version": "vaguehydro.change_artifact_archive.v1", "created_at": time.time(), "report_count": len(files), "artifact_count": len(records), "downloaded": sum(item["status"] == "downloaded" for item in records), "failed": sum(item["status"] == "failed" for item in records), "records": records}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "ARCHIVE_MANIFEST.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("report_count", "artifact_count", "downloaded", "failed")}, ensure_ascii=False))
    return 0 if args.inventory_only or summary["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

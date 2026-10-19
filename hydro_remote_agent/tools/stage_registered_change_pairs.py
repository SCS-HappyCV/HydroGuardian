from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage registered before/after image pairs from the DTXX grid CSV.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = []
    errors = []
    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            before = Path(row["2018影像"])
            after = Path(row["2023影像"])
            expected = (int(row["宽度像素"]), int(row["高度像素"]))
            if not before.is_file():
                errors.append(f"missing before: {before}")
            if not after.is_file():
                errors.append(f"missing after: {after}")
            rows.append({
                "pair_id": row["文件名"],
                "grid_row": int(row["行(南到北)"]),
                "grid_col": int(row["列(西到东)"]),
                "before_image_path": str(before),
                "after_image_path": str(after),
                "width": expected[0],
                "height": expected[1],
                "x_min": float(row["X最小"]),
                "y_min": float(row["Y最小"]),
                "x_max": float(row["X最大"]),
                "y_max": float(row["Y最大"]),
                "registration_source": "影像_4x4_对应关系.csv",
            })
    dims = {(item["width"], item["height"]) for item in rows}
    if len(rows) != 16:
        errors.append(f"expected 16 pairs, found {len(rows)}")
    if dims != {(17500, 17292)}:
        errors.append(f"unexpected dimensions: {sorted(dims)}")
    report = {"schema_version": "vaguehydro.registered_change_pairs.v1", "status": "passed" if not errors else "failed", "pair_count": len(rows), "dimensions": sorted([list(item) for item in dims]), "pairs": rows, "errors": errors}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "pair_count": len(rows), "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

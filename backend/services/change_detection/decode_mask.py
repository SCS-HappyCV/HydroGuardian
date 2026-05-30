import base64
import json
import sys
from typing import Any, Dict


def save_mask_base64(mask_base64: str, out_path: str) -> None:
    """Decode base64 PNG bytes and write to disk."""
    png_bytes = base64.b64decode(mask_base64)
    with open(out_path, "wb") as f:
        f.write(png_bytes)


def load_mask_from_json(path: str) -> str:
    """Load mask_base64 from a JSON file produced by the /predict API."""
    with open(path, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)
    if "mask_base64" not in data:
        raise KeyError("mask_base64 not found in JSON response")
    return data["mask_base64"]


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python decode_mask.py <response.json> <out.png>")
        sys.exit(1)

    json_path = sys.argv[1]
    out_path = sys.argv[2]

    mask_base64 = load_mask_from_json(json_path)
    save_mask_base64(mask_base64, out_path)
    print(f"Saved mask to {out_path}")

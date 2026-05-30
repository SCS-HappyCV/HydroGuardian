from __future__ import annotations

import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
ALGORITHM_ROOT = SERVICE_ROOT / "algorithm"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))
if str(ALGORITHM_ROOT) not in sys.path:
    sys.path.insert(0, str(ALGORITHM_ROOT))

from web.app import create_app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    from web.config import load_settings

    settings = load_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)

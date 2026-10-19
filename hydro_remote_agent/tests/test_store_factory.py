from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.store_factory import create_job_store


class StoreFactoryTest(unittest.TestCase):
    def test_sqlite_path_uses_existing_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_job_store(Path(temp_dir) / "jobs.sqlite")
            self.assertIsInstance(store, JobStore)

    def test_postgres_url_selects_postgres_store(self) -> None:
        with patch("hydro_remote_agent.service.postgres_store.PostgresJobStore") as store_class:
            create_job_store("postgresql://user:pass@db/app")
            store_class.assert_called_once_with("postgresql://user:pass@db/app")


if __name__ == "__main__":
    unittest.main()

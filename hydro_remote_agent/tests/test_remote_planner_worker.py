from __future__ import annotations

import unittest

from unittest.mock import patch

from hydro_remote_agent.tools.remote_planner_worker import _planner_submission, _preview_url, _rewrite_download_url


class RemotePlannerWorkerTest(unittest.TestCase):
    def test_rewrites_only_download_origin_for_secure_tunnel(self) -> None:
        original = "http://agent.example.internal:9000/assets/item.png?signature=abc&expires=123"
        rewritten = _rewrite_download_url(original, "http://127.0.0.1:29000")
        self.assertEqual(
            rewritten,
            "http://127.0.0.1:29000/assets/item.png?signature=abc&expires=123",
        )

    def test_keeps_original_download_url_without_override(self) -> None:
        original = "http://storage:9000/assets/item.png?signature=abc"
        self.assertEqual(_rewrite_download_url(original, None), original)

    def test_builds_preview_url_through_control_tunnel(self) -> None:
        self.assertEqual(
            _preview_url(
                "http://172.16.224.4:18080",
                "artifact://art-image",
                "http://127.0.0.1:28080",
            ),
            "http://127.0.0.1:28080/v1/assets/art-image/preview?max_dimension=2048",
        )

    @patch("hydro_remote_agent.tools.remote_planner_worker._download_url")
    def test_planner_uses_preview_but_restores_original_asset_references(self, download_url) -> None:
        submission = {
            "request_id": "preview-1",
            "query": "检查变化",
            "assets": {
                "image_path": "artifact://art-image",
                "point_cloud_path": "artifact://art-cloud",
            },
        }
        resolved, reverse = _planner_submission(
            "http://control:18080", submission, "secret", "planner",
            "http://127.0.0.1:28080", 2048,
        )
        preview = "http://127.0.0.1:28080/v1/assets/art-image/preview?max_dimension=2048"
        self.assertEqual(resolved["assets"]["image_path"], preview)
        self.assertEqual(resolved["assets"]["point_cloud_path"], "artifact://art-cloud")
        self.assertEqual(reverse, {preview: "artifact://art-image"})
        download_url.assert_not_called()

if __name__ == "__main__":
    unittest.main()

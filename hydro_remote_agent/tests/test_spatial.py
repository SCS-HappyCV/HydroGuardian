from __future__ import annotations

import unittest
from pathlib import Path

from hydro_remote_agent.service.spatial import (
    enrich_pixel_regions,
    inspect_geotiff,
    inspect_las,
    pixel_to_geographic,
    pixel_to_projected,
    projected_to_geographic,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = PACKAGE_ROOT / "test_data"


class SpatialMetadataTest(unittest.TestCase):
    def test_cgcs2000_gauss_kruger_inverse(self) -> None:
        longitude, latitude = projected_to_geographic(360659.1634835815, 2610027.617910156, 4546)
        self.assertAlmostEqual(longitude, 109.635007384, places=7)
        self.assertAlmostEqual(latitude, 23.585344832, places=7)

    def test_pixel_conversion_and_region_enrichment(self) -> None:
        spatial = {
            "schema_version": "hydro-spatial.v1",
            "source_type": "raster",
            "crs": {"code": 4546},
            "raster": {"transform": [0.1, 0.0, 359784.0, 0.0, -0.1, 2610892.0]},
        }
        self.assertEqual(pixel_to_projected(spatial, 10, 20), (359785.0, 2610890.0))
        geographic = pixel_to_geographic(spatial, 10, 20)
        self.assertIsNotNone(geographic)
        result = enrich_pixel_regions({
            "regions": [{"region_id": 1, "bbox_xywh": [10, 20, 30, 40], "centroid_xy": [25, 40]}],
        }, spatial)
        region_spatial = result["regions"][0]["spatial"]
        self.assertIn("projected_bbox", region_spatial)
        self.assertIn("geographic_center", region_spatial)

    def test_real_geotiff_and_las_are_aligned(self) -> None:
        raster_path = TEST_DATA / "R01_C01_2023.tif"
        las_path = TEST_DATA / "R01_C01.las"
        if not raster_path.exists() or not las_path.exists():
            self.skipTest("real spatial fixtures are unavailable")
        raster = inspect_geotiff(raster_path, "after_image_path")
        point_cloud = inspect_las(las_path, "point_cloud_path")
        self.assertEqual(raster["crs"]["code"], 4546)
        self.assertEqual(point_cloud["crs"]["code"], 4546)
        self.assertTrue(point_cloud["crs"]["normalized"])
        raster_bounds = raster["extent"]["projected"]
        point_bounds = point_cloud["extent"]["projected"]
        for key in ("min_x", "min_y", "max_x", "max_y"):
            self.assertLess(abs(raster_bounds[key] - point_bounds[key]), 0.01)
        self.assertEqual(point_cloud["point_cloud"]["point_count"], 4782143)


if __name__ == "__main__":
    unittest.main()

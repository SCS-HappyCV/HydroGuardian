from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


SPATIAL_SCHEMA_VERSION = "hydro-spatial.v1"
SPATIAL_CONTEXT_SCHEMA_VERSION = "hydro-spatial-context.v1"

_TIFF_TYPE_FORMATS = {
    1: ("B", 1),
    2: ("c", 1),
    3: ("H", 2),
    4: ("I", 4),
    5: ("II", 8),
    11: ("f", 4),
    12: ("d", 8),
}


def _extent_payload(bounds: Sequence[float], epsg: int) -> Dict[str, Any]:
    minimum_x, minimum_y, maximum_x, maximum_y = (float(value) for value in bounds)
    projected = {
        "min_x": minimum_x,
        "min_y": minimum_y,
        "max_x": maximum_x,
        "max_y": maximum_y,
        "center_x": (minimum_x + maximum_x) / 2.0,
        "center_y": (minimum_y + maximum_y) / 2.0,
    }
    corners = [
        projected_to_geographic(minimum_x, minimum_y, epsg),
        projected_to_geographic(maximum_x, maximum_y, epsg),
    ]
    geographic = None
    if all(item is not None for item in corners):
        southwest, northeast = corners
        geographic = {
            "west": southwest[0],
            "south": southwest[1],
            "east": northeast[0],
            "north": northeast[1],
            "center_lon": (southwest[0] + northeast[0]) / 2.0,
            "center_lat": (southwest[1] + northeast[1]) / 2.0,
        }
    return {"projected": projected, "geographic": geographic}


def _crs_payload(epsg: int, *, source: str, declared_epsg: Optional[int] = None) -> Dict[str, Any]:
    names = {
        4546: "CGCS2000 / 3-degree Gauss-Kruger CM 111E",
        4490: "China Geodetic Coordinate System 2000",
        4326: "WGS 84",
    }
    return {
        "authority": "EPSG",
        "code": epsg,
        "name": names.get(epsg, f"EPSG:{epsg}"),
        "horizontal_unit": "metre" if epsg == 4546 else "degree",
        "source": source,
        "declared_code": declared_epsg,
        "normalized": declared_epsg is not None and declared_epsg != epsg,
    }


def _read_tiff_values(handle, endian: str, field_type: int, count: int, value_field: bytes) -> Any:
    definition = _TIFF_TYPE_FORMATS.get(field_type)
    if definition is None:
        return None
    format_code, size = definition
    total_size = size * count
    if total_size <= 4:
        raw = value_field[:total_size]
    else:
        offset = struct.unpack(endian + "I", value_field)[0]
        current = handle.tell()
        handle.seek(offset)
        raw = handle.read(total_size)
        handle.seek(current)
    if len(raw) != total_size:
        return None
    if field_type == 2:
        return raw.rstrip(b"\0").decode("utf-8", errors="replace")
    if field_type == 5:
        values = []
        for index in range(count):
            numerator, denominator = struct.unpack_from(endian + "II", raw, index * 8)
            values.append(numerator / denominator if denominator else 0.0)
    else:
        values = list(struct.unpack(endian + format_code * count, raw))
    return values[0] if count == 1 else values


def _read_tiff_tags(path: Path) -> Dict[int, Any]:
    with path.open("rb") as handle:
        byte_order = handle.read(2)
        if byte_order == b"II":
            endian = "<"
        elif byte_order == b"MM":
            endian = ">"
        else:
            raise ValueError("Unsupported TIFF byte order")
        if struct.unpack(endian + "H", handle.read(2))[0] != 42:
            raise ValueError("Only classic TIFF files are supported")
        first_ifd = struct.unpack(endian + "I", handle.read(4))[0]
        handle.seek(first_ifd)
        entry_count = struct.unpack(endian + "H", handle.read(2))[0]
        tags: Dict[int, Any] = {}
        for _ in range(entry_count):
            entry = handle.read(12)
            if len(entry) != 12:
                break
            tag, field_type, count = struct.unpack(endian + "HHI", entry[:8])
            value = _read_tiff_values(handle, endian, field_type, count, entry[8:12])
            if value is not None:
                tags[tag] = value
        return tags


def _geo_keys(directory: Any) -> Dict[int, Tuple[int, int, int]]:
    if not isinstance(directory, list) or len(directory) < 4:
        return {}
    keys: Dict[int, Tuple[int, int, int]] = {}
    for index in range(int(directory[3])):
        start = 4 + index * 4
        if start + 4 <= len(directory):
            key_id, location, count, offset = directory[start:start + 4]
            keys[int(key_id)] = (int(location), int(count), int(offset))
    return keys


def inspect_geotiff(path: str | Path, role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    source = Path(path)
    tags = _read_tiff_tags(source)
    width = int(tags.get(256, 0))
    height = int(tags.get(257, 0))
    scale = tags.get(33550)
    tiepoint = tags.get(33922)
    keys = _geo_keys(tags.get(34735))
    projected_key = keys.get(3072)
    epsg = projected_key[2] if projected_key and projected_key[0] == 0 else None
    if not width or not height or not isinstance(scale, list) or not isinstance(tiepoint, list) or len(scale) < 2 or len(tiepoint) < 6 or not epsg:
        return None
    origin_x = float(tiepoint[3]) - float(tiepoint[0]) * float(scale[0])
    origin_y = float(tiepoint[4]) + float(tiepoint[1]) * float(scale[1])
    pixel_x = float(scale[0])
    pixel_y = float(scale[1])
    bounds = (origin_x, origin_y - height * pixel_y, origin_x + width * pixel_x, origin_y)
    return {
        "schema_version": SPATIAL_SCHEMA_VERSION,
        "source_type": "raster",
        "asset_role": role,
        "crs": _crs_payload(int(epsg), source="geotiff"),
        "extent": _extent_payload(bounds, int(epsg)),
        "raster": {
            "width": width,
            "height": height,
            "pixel_size_x": pixel_x,
            "pixel_size_y": pixel_y,
            "origin_x": origin_x,
            "origin_y": origin_y,
            "transform": [pixel_x, 0.0, origin_x, 0.0, -pixel_y, origin_y],
            "pixel_reference": "upper_left_corner",
        },
    }


def _las_geo_values(payloads: Mapping[int, bytes]) -> Tuple[Dict[int, Tuple[int, int, int]], Sequence[float]]:
    directory_payload = payloads.get(34735, b"")
    doubles_payload = payloads.get(34736, b"")
    if len(directory_payload) % 2:
        return {}, ()
    directory = list(struct.unpack("<" + "H" * (len(directory_payload) // 2), directory_payload))
    doubles = struct.unpack("<" + "d" * (len(doubles_payload) // 8), doubles_payload) if doubles_payload else ()
    return _geo_keys(directory), doubles


def _geo_double(keys: Mapping[int, Tuple[int, int, int]], doubles: Sequence[float], key_id: int) -> Optional[float]:
    key = keys.get(key_id)
    if key is None or key[0] != 34736 or key[2] >= len(doubles):
        return None
    return float(doubles[key[2]])


def _infer_las_projected_epsg(keys: Mapping[int, Tuple[int, int, int]], doubles: Sequence[float]) -> Tuple[Optional[int], Optional[int]]:
    geographic = keys.get(2048)
    declared_geographic = geographic[2] if geographic and geographic[0] == 0 else None
    projected = keys.get(3072)
    if projected and projected[0] == 0 and projected[2] not in {0, 32767}:
        return projected[2], declared_geographic
    transform = keys.get(3075)
    linear_units = keys.get(3076)
    matches_4546 = (
        declared_geographic == 4490
        and transform is not None and transform[2] == 1
        and linear_units is not None and linear_units[2] == 9001
        and math.isclose(_geo_double(keys, doubles, 3080) or 0.0, 111.0, abs_tol=1e-9)
        and math.isclose(_geo_double(keys, doubles, 3081) or 0.0, 0.0, abs_tol=1e-9)
        and math.isclose(_geo_double(keys, doubles, 3082) or 0.0, 500000.0, abs_tol=1e-6)
        and math.isclose(_geo_double(keys, doubles, 3083) or 0.0, 0.0, abs_tol=1e-6)
        and math.isclose(_geo_double(keys, doubles, 3092) or 0.0, 1.0, abs_tol=1e-12)
    )
    return (4546 if matches_4546 else None), declared_geographic


def inspect_las(path: str | Path, role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    source = Path(path)
    with source.open("rb") as handle:
        header = handle.read(227)
        if len(header) < 227 or header[:4] != b"LASF":
            return None
        header_size = struct.unpack_from("<H", header, 94)[0]
        vlr_count = struct.unpack_from("<I", header, 100)[0]
        point_format = header[104] & 0x3F
        point_count = struct.unpack_from("<I", header, 107)[0]
        scales = struct.unpack_from("<ddd", header, 131)
        offsets = struct.unpack_from("<ddd", header, 155)
        maximum_x, minimum_x, maximum_y, minimum_y, maximum_z, minimum_z = struct.unpack_from("<dddddd", header, 179)
        handle.seek(header_size)
        payloads: Dict[int, bytes] = {}
        for _ in range(vlr_count):
            vlr_header = handle.read(54)
            if len(vlr_header) != 54:
                break
            user_id = vlr_header[2:18].rstrip(b"\0").decode("ascii", errors="ignore")
            record_id, length = struct.unpack_from("<HH", vlr_header, 18)
            payload = handle.read(length)
            if user_id == "LASF_Projection":
                payloads[record_id] = payload
    keys, doubles = _las_geo_values(payloads)
    epsg, declared_geographic = _infer_las_projected_epsg(keys, doubles)
    if epsg is None:
        return None
    return {
        "schema_version": SPATIAL_SCHEMA_VERSION,
        "source_type": "point_cloud",
        "asset_role": role,
        "crs": _crs_payload(epsg, source="las_geokeys", declared_epsg=declared_geographic),
        "extent": _extent_payload((minimum_x, minimum_y, maximum_x, maximum_y), epsg),
        "point_cloud": {
            "point_count": int(point_count),
            "point_format": int(point_format),
            "scale_x": float(scales[0]),
            "scale_y": float(scales[1]),
            "scale_z": float(scales[2]),
            "offset_x": float(offsets[0]),
            "offset_y": float(offsets[1]),
            "offset_z": float(offsets[2]),
            "elevation_min": float(minimum_z),
            "elevation_max": float(maximum_z),
        },
    }


def normalize_spatial_metadata(value: Mapping[str, Any], role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if value.get("schema_version") != SPATIAL_SCHEMA_VERSION or not isinstance(value.get("crs"), Mapping):
        return None
    normalized = dict(value)
    if role:
        normalized["asset_role"] = role
    return normalized


def inspect_spatial_asset(path: str | Path, role: Optional[str] = None, inherited: Optional[Mapping[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if inherited:
        normalized = normalize_spatial_metadata(inherited, role)
        if normalized:
            return normalized
    suffix = Path(path).suffix.lower()
    try:
        if suffix in {".tif", ".tiff"}:
            return inspect_geotiff(path, role)
        if suffix in {".las"}:
            return inspect_las(path, role)
    except (OSError, ValueError, struct.error):
        return None
    return None


def projected_to_geographic(x: float, y: float, epsg: int) -> Optional[Tuple[float, float]]:
    if epsg in {4326, 4490}:
        return float(x), float(y)
    if epsg != 4546:
        return None
    semi_major = 6378137.0
    flattening = 1.0 / 298.257222101
    eccentricity_squared = flattening * (2.0 - flattening)
    second_eccentricity_squared = eccentricity_squared / (1.0 - eccentricity_squared)
    central_meridian = math.radians(111.0)
    meridional_arc = float(y)
    mu = meridional_arc / (
        semi_major
        * (1.0 - eccentricity_squared / 4.0 - 3.0 * eccentricity_squared ** 2 / 64.0 - 5.0 * eccentricity_squared ** 3 / 256.0)
    )
    e1 = (1.0 - math.sqrt(1.0 - eccentricity_squared)) / (1.0 + math.sqrt(1.0 - eccentricity_squared))
    footprint = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1 ** 3 / 32.0) * math.sin(2.0 * mu)
        + (21.0 * e1 ** 2 / 16.0 - 55.0 * e1 ** 4 / 32.0) * math.sin(4.0 * mu)
        + (151.0 * e1 ** 3 / 96.0) * math.sin(6.0 * mu)
        + (1097.0 * e1 ** 4 / 512.0) * math.sin(8.0 * mu)
    )
    sin_footprint = math.sin(footprint)
    cos_footprint = math.cos(footprint)
    tangent_squared = math.tan(footprint) ** 2
    curvature = second_eccentricity_squared * cos_footprint ** 2
    prime_vertical = semi_major / math.sqrt(1.0 - eccentricity_squared * sin_footprint ** 2)
    meridional_radius = semi_major * (1.0 - eccentricity_squared) / (1.0 - eccentricity_squared * sin_footprint ** 2) ** 1.5
    d = (float(x) - 500000.0) / prime_vertical
    latitude = footprint - (prime_vertical * math.tan(footprint) / meridional_radius) * (
        d ** 2 / 2.0
        - (5.0 + 3.0 * tangent_squared + 10.0 * curvature - 4.0 * curvature ** 2 - 9.0 * second_eccentricity_squared) * d ** 4 / 24.0
        + (61.0 + 90.0 * tangent_squared + 298.0 * curvature + 45.0 * tangent_squared ** 2 - 252.0 * second_eccentricity_squared - 3.0 * curvature ** 2) * d ** 6 / 720.0
    )
    longitude = central_meridian + (
        d
        - (1.0 + 2.0 * tangent_squared + curvature) * d ** 3 / 6.0
        + (5.0 - 2.0 * curvature + 28.0 * tangent_squared - 3.0 * curvature ** 2 + 8.0 * second_eccentricity_squared + 24.0 * tangent_squared ** 2) * d ** 5 / 120.0
    ) / cos_footprint
    return math.degrees(longitude), math.degrees(latitude)


def pixel_to_projected(spatial: Mapping[str, Any], x: float, y: float) -> Optional[Tuple[float, float]]:
    raster = spatial.get("raster")
    if not isinstance(raster, Mapping):
        return None
    transform = raster.get("transform")
    if not isinstance(transform, list) or len(transform) != 6:
        return None
    a, b, c, d, e, f = (float(value) for value in transform)
    return a * x + b * y + c, d * x + e * y + f


def pixel_to_geographic(spatial: Mapping[str, Any], x: float, y: float) -> Optional[Tuple[float, float]]:
    projected = pixel_to_projected(spatial, x, y)
    crs = spatial.get("crs")
    if projected is None or not isinstance(crs, Mapping) or not isinstance(crs.get("code"), int):
        return None
    return projected_to_geographic(projected[0], projected[1], int(crs["code"]))


def enrich_pixel_regions(payload: Mapping[str, Any], spatial: Mapping[str, Any]) -> Dict[str, Any]:
    enriched = dict(payload)
    enriched["spatial_reference"] = dict(spatial)
    regions = []
    for raw in payload.get("regions", []) if isinstance(payload.get("regions"), list) else []:
        if not isinstance(raw, Mapping):
            continue
        region = dict(raw)
        bbox = raw.get("bbox_xywh")
        centroid = raw.get("centroid_xy")
        spatial_region: Dict[str, Any] = {}
        if isinstance(bbox, list) and len(bbox) == 4:
            x, y, width, height = (float(value) for value in bbox)
            upper_left = pixel_to_projected(spatial, x, y)
            lower_right = pixel_to_projected(spatial, x + width, y + height)
            geo_upper_left = pixel_to_geographic(spatial, x, y)
            geo_lower_right = pixel_to_geographic(spatial, x + width, y + height)
            if upper_left and lower_right:
                spatial_region["projected_bbox"] = {
                    "min_x": min(upper_left[0], lower_right[0]), "min_y": min(upper_left[1], lower_right[1]),
                    "max_x": max(upper_left[0], lower_right[0]), "max_y": max(upper_left[1], lower_right[1]),
                }
            if geo_upper_left and geo_lower_right:
                spatial_region["geographic_bbox"] = {
                    "west": min(geo_upper_left[0], geo_lower_right[0]), "south": min(geo_upper_left[1], geo_lower_right[1]),
                    "east": max(geo_upper_left[0], geo_lower_right[0]), "north": max(geo_upper_left[1], geo_lower_right[1]),
                }
        if isinstance(centroid, list) and len(centroid) == 2:
            projected_center = pixel_to_projected(spatial, float(centroid[0]), float(centroid[1]))
            geographic_center = pixel_to_geographic(spatial, float(centroid[0]), float(centroid[1]))
            if projected_center:
                spatial_region["projected_center"] = {"x": projected_center[0], "y": projected_center[1]}
            if geographic_center:
                spatial_region["geographic_center"] = {"longitude": geographic_center[0], "latitude": geographic_center[1]}
        if spatial_region:
            region["spatial"] = spatial_region
        regions.append(region)
    enriched["regions"] = regions
    return enriched

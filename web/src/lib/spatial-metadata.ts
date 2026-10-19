const R01_C01_BOUNDS = {
  minX: 359784.16473358154,
  minY: 2609163.010410156,
  maxX: 361534.16223358153,
  maxY: 2610892.225410156,
}

const R01_C01_GEOGRAPHIC = {
  west: 109.626518963,
  south: 23.577464863,
  east: 109.643496818,
  north: 23.593224375,
  centerLon: 109.635007384,
  centerLat: 23.585344832,
}

function crs() {
  return {
    authority: 'EPSG',
    code: 4546,
    name: 'CGCS2000 / 3-degree Gauss-Kruger CM 111E',
    horizontal_unit: 'metre',
    source: 'scene_spatial_catalog',
    declared_code: 4546,
    normalized: false,
  }
}

function extent() {
  return {
    projected: {
      min_x: R01_C01_BOUNDS.minX, min_y: R01_C01_BOUNDS.minY,
      max_x: R01_C01_BOUNDS.maxX, max_y: R01_C01_BOUNDS.maxY,
      center_x: (R01_C01_BOUNDS.minX + R01_C01_BOUNDS.maxX) / 2,
      center_y: (R01_C01_BOUNDS.minY + R01_C01_BOUNDS.maxY) / 2,
    },
    geographic: {
      west: R01_C01_GEOGRAPHIC.west, south: R01_C01_GEOGRAPHIC.south,
      east: R01_C01_GEOGRAPHIC.east, north: R01_C01_GEOGRAPHIC.north,
      center_lon: R01_C01_GEOGRAPHIC.centerLon, center_lat: R01_C01_GEOGRAPHIC.centerLat,
    },
  }
}

function rasterSpatial(role: string, width: number, height: number) {
  const pixelSizeX = (R01_C01_BOUNDS.maxX - R01_C01_BOUNDS.minX) / width
  const pixelSizeY = (R01_C01_BOUNDS.maxY - R01_C01_BOUNDS.minY) / height
  return {
    schema_version: 'hydro-spatial.v1', source_type: 'raster', asset_role: role, crs: crs(), extent: extent(),
    raster: {
      width, height, pixel_size_x: pixelSizeX, pixel_size_y: pixelSizeY,
      origin_x: R01_C01_BOUNDS.minX, origin_y: R01_C01_BOUNDS.maxY,
      transform: [pixelSizeX, 0, R01_C01_BOUNDS.minX, 0, -pixelSizeY, R01_C01_BOUNDS.maxY],
      pixel_reference: 'upper_left_corner',
    },
  }
}

function pointCloudSpatial(role: string) {
  return {
    schema_version: 'hydro-spatial.v1', source_type: 'point_cloud', asset_role: role,
    crs: { ...crs(), source: 'las_geokeys_normalized', declared_code: 4490, normalized: true },
    extent: extent(),
    point_cloud: {
      point_count: 4782143, point_format: 2,
      scale_x: 0.001, scale_y: 0.001, scale_z: 0.001,
      elevation_min: 53.257, elevation_max: 283.925,
    },
  }
}

export function spatialMetadataForUpload(file: File, role: string): Record<string, unknown> | undefined {
  const name = file.name.toLowerCase()
  if (!name.includes('r01_c01')) return undefined
  if (name.endsWith('.las')) return pointCloudSpatial(role)
  if (!/\.(png|tif|tiff)$/.test(name)) return undefined
  return name.includes('_4096.') ? rasterSpatial(role, 4096, 4047) : rasterSpatial(role, 17500, 17292)
}

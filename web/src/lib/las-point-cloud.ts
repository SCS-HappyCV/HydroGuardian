export interface LasHeader {
  version: string
  pointDataOffset: number
  pointFormat: number
  pointRecordLength: number
  pointCount: number
  scale: [number, number, number]
  offset: [number, number, number]
  bounds: {
    minX: number
    minY: number
    minZ: number
    maxX: number
    maxY: number
    maxZ: number
  }
}

export interface PointCloudData {
  header: LasHeader
  positions: Float32Array
  colors: Float32Array
  sourceIndices: Uint32Array
  renderedPointCount: number
}

const colorOffsets: Record<number, number> = { 2: 20, 3: 28, 5: 28, 7: 30, 8: 30, 10: 30 }

function uint64(view: DataView, offset: number): number {
  if (typeof view.getBigUint64 === 'function') return Number(view.getBigUint64(offset, true))
  return view.getUint32(offset, true) + view.getUint32(offset + 4, true) * 2 ** 32
}

export function parseLasHeader(buffer: ArrayBuffer): LasHeader {
  if (buffer.byteLength < 227) throw new Error('LAS 文件头不完整')
  const signature = new TextDecoder().decode(new Uint8Array(buffer, 0, 4))
  if (signature !== 'LASF') throw new Error('当前文件不是有效的 LAS 点云')
  const view = new DataView(buffer)
  const versionMajor = view.getUint8(24)
  const versionMinor = view.getUint8(25)
  const pointDataOffset = view.getUint32(96, true)
  const pointFormat = view.getUint8(104) & 0x3f
  const pointRecordLength = view.getUint16(105, true)
  const legacyCount = view.getUint32(107, true)
  const extendedCount = buffer.byteLength >= 255 && versionMajor === 1 && versionMinor >= 4 ? uint64(view, 247) : 0
  return {
    version: `${versionMajor}.${versionMinor}`,
    pointDataOffset,
    pointFormat,
    pointRecordLength,
    pointCount: extendedCount || legacyCount,
    scale: [view.getFloat64(131, true), view.getFloat64(139, true), view.getFloat64(147, true)],
    offset: [view.getFloat64(155, true), view.getFloat64(163, true), view.getFloat64(171, true)],
    bounds: {
      maxX: view.getFloat64(179, true),
      minX: view.getFloat64(187, true),
      maxY: view.getFloat64(195, true),
      minY: view.getFloat64(203, true),
      maxZ: view.getFloat64(211, true),
      minZ: view.getFloat64(219, true),
    },
  }
}

function heightColor(value: number): [number, number, number] {
  const t = Math.min(1, Math.max(0, value))
  if (t < 0.35) return [0.08 + t * 0.35, 0.58 + t * 0.72, 0.86]
  if (t < 0.68) return [0.2 + t * 0.55, 0.82, 0.65 - t * 0.35]
  return [0.75 + t * 0.25, 0.78 - (t - 0.68) * 1.2, 0.25]
}

function decodeRecords(
  buffer: ArrayBuffer,
  header: LasHeader,
  count: number,
  sourceOffset: number,
  positions: number[],
  colors: number[],
  sourceIndices: number[],
  sourceIndexStart: number,
) {
  const view = new DataView(buffer)
  const centerX = (header.bounds.minX + header.bounds.maxX) / 2
  const centerY = (header.bounds.minY + header.bounds.maxY) / 2
  const centerZ = (header.bounds.minZ + header.bounds.maxZ) / 2
  const span = Math.max(header.bounds.maxX - header.bounds.minX, header.bounds.maxY - header.bounds.minY, 1)
  const zSpan = Math.max(header.bounds.maxZ - header.bounds.minZ, 1)
  const colorOffset = colorOffsets[header.pointFormat]
  const available = Math.min(count, Math.floor((buffer.byteLength - sourceOffset) / header.pointRecordLength))
  for (let index = 0; index < available; index += 1) {
    const cursor = sourceOffset + index * header.pointRecordLength
    const x = view.getInt32(cursor, true) * header.scale[0] + header.offset[0]
    const y = view.getInt32(cursor + 4, true) * header.scale[1] + header.offset[1]
    const z = view.getInt32(cursor + 8, true) * header.scale[2] + header.offset[2]
    sourceIndices.push(sourceIndexStart + index)
    positions.push((x - centerX) / span * 2, (z - centerZ) / span * 2, -(y - centerY) / span * 2)
    if (colorOffset !== undefined && cursor + colorOffset + 6 <= buffer.byteLength) {
      const red = view.getUint16(cursor + colorOffset, true)
      const green = view.getUint16(cursor + colorOffset + 2, true)
      const blue = view.getUint16(cursor + colorOffset + 4, true)
      const divisor = Math.max(red, green, blue) > 255 ? 65535 : 255
      colors.push(red / divisor, green / divisor, blue / divisor)
    } else {
      colors.push(...heightColor((z - header.bounds.minZ) / zSpan))
    }
  }
}

async function rangedFetch(url: string, start: number, end: number, signal?: AbortSignal): Promise<Response> {
  const response = await fetch(url, { headers: { Range: `bytes=${start}-${end}` }, signal })
  if (!response.ok) throw new Error(`点云读取失败（${response.status}）`)
  return response
}

export async function loadLasPointCloud(
  url: string,
  maxPoints = 240000,
  signal?: AbortSignal,
  onProgress?: (progress: number) => void,
  preferCompleteScene = false,
): Promise<PointCloudData> {
  if (preferCompleteScene) {
    const response = await fetch(url, { signal })
    if (!response.ok) throw new Error(`点云读取失败（${response.status}）`)
    const buffer = await response.arrayBuffer()
    return loadLasPointCloudFromBuffer(buffer, maxPoints, onProgress)
  }
  const headerResponse = await rangedFetch(url, 0, 374, signal)
  const headerBuffer = await headerResponse.arrayBuffer()
  const header = parseLasHeader(headerBuffer)
  if (!header.pointCount || !header.pointRecordLength) throw new Error('LAS 文件没有可读取的点记录')
  const positions: number[] = []
  const colors: number[] = []
  const sourceIndices: number[] = []

  if (headerResponse.status === 200) {
    const stride = Math.max(1, Math.ceil(header.pointCount / maxPoints))
    const view = new DataView(headerBuffer)
    const sampled = Math.ceil(header.pointCount / stride)
    const centerX = (header.bounds.minX + header.bounds.maxX) / 2
    const centerY = (header.bounds.minY + header.bounds.maxY) / 2
    const centerZ = (header.bounds.minZ + header.bounds.maxZ) / 2
    const span = Math.max(header.bounds.maxX - header.bounds.minX, header.bounds.maxY - header.bounds.minY, 1)
    const zSpan = Math.max(header.bounds.maxZ - header.bounds.minZ, 1)
    const colorOffset = colorOffsets[header.pointFormat]
    for (let outputIndex = 0, pointIndex = 0; outputIndex < sampled && pointIndex < header.pointCount; outputIndex += 1, pointIndex += stride) {
      const cursor = header.pointDataOffset + pointIndex * header.pointRecordLength
      if (cursor + header.pointRecordLength > view.byteLength) break
      const x = view.getInt32(cursor, true) * header.scale[0] + header.offset[0]
      const y = view.getInt32(cursor + 4, true) * header.scale[1] + header.offset[1]
      const z = view.getInt32(cursor + 8, true) * header.scale[2] + header.offset[2]
      sourceIndices.push(pointIndex)
      positions.push((x - centerX) / span * 2, (z - centerZ) / span * 2, -(y - centerY) / span * 2)
      if (colorOffset !== undefined && cursor + colorOffset + 6 <= view.byteLength) {
        const red = view.getUint16(cursor + colorOffset, true)
        const green = view.getUint16(cursor + colorOffset + 2, true)
        const blue = view.getUint16(cursor + colorOffset + 4, true)
        const divisor = Math.max(red, green, blue) > 255 ? 65535 : 255
        colors.push(red / divisor, green / divisor, blue / divisor)
      } else colors.push(...heightColor((z - header.bounds.minZ) / zSpan))
      if (outputIndex % 12000 === 0) onProgress?.(Math.round(outputIndex / sampled * 100))
    }
  } else {
    const chunkCount = Math.min(24, Math.max(1, Math.ceil(header.pointCount / 10000)))
    const pointsPerChunk = Math.max(1, Math.floor(maxPoints / chunkCount))
    for (let chunkIndex = 0; chunkIndex < chunkCount; chunkIndex += 1) {
      const startPoint = chunkCount === 1 ? 0 : Math.floor((header.pointCount - pointsPerChunk) * chunkIndex / (chunkCount - 1))
      const count = Math.min(pointsPerChunk, header.pointCount - startPoint)
      const start = header.pointDataOffset + startPoint * header.pointRecordLength
      const end = start + count * header.pointRecordLength - 1
      const response = await rangedFetch(url, start, end, signal)
      const buffer = await response.arrayBuffer()
      if (response.status === 200) {
        return loadLasPointCloudFromBuffer(buffer, maxPoints, onProgress)
      }
      decodeRecords(buffer, header, count, 0, positions, colors, sourceIndices, startPoint)
      onProgress?.(Math.round((chunkIndex + 1) / chunkCount * 100))
    }
  }

  return {
    header,
    positions: new Float32Array(positions),
    colors: new Float32Array(colors),
    sourceIndices: new Uint32Array(sourceIndices),
    renderedPointCount: positions.length / 3,
  }
}

export function loadLasPointCloudFromBuffer(buffer: ArrayBuffer, maxPoints = 240000, onProgress?: (progress: number) => void): PointCloudData {
  const header = parseLasHeader(buffer)
  const stride = Math.max(1, Math.ceil(header.pointCount / maxPoints))
  const positions: number[] = []
  const colors: number[] = []
  const sourceIndices: number[] = []
  const view = new DataView(buffer)
  const centerX = (header.bounds.minX + header.bounds.maxX) / 2
  const centerY = (header.bounds.minY + header.bounds.maxY) / 2
  const centerZ = (header.bounds.minZ + header.bounds.maxZ) / 2
  const span = Math.max(header.bounds.maxX - header.bounds.minX, header.bounds.maxY - header.bounds.minY, 1)
  const zSpan = Math.max(header.bounds.maxZ - header.bounds.minZ, 1)
  const colorOffset = colorOffsets[header.pointFormat]
  for (let point = 0; point < header.pointCount; point += stride) {
    const cursor = header.pointDataOffset + point * header.pointRecordLength
    if (cursor + header.pointRecordLength > buffer.byteLength) break
    const x = view.getInt32(cursor, true) * header.scale[0] + header.offset[0]
    const y = view.getInt32(cursor + 4, true) * header.scale[1] + header.offset[1]
    const z = view.getInt32(cursor + 8, true) * header.scale[2] + header.offset[2]
    sourceIndices.push(point)
    positions.push((x - centerX) / span * 2, (z - centerZ) / span * 2, -(y - centerY) / span * 2)
    if (colorOffset !== undefined && cursor + colorOffset + 6 <= buffer.byteLength) {
      const red = view.getUint16(cursor + colorOffset, true)
      const green = view.getUint16(cursor + colorOffset + 2, true)
      const blue = view.getUint16(cursor + colorOffset + 4, true)
      const divisor = Math.max(red, green, blue) > 255 ? 65535 : 255
      colors.push(red / divisor, green / divisor, blue / divisor)
    } else colors.push(...heightColor((z - header.bounds.minZ) / zSpan))
    if (point % (stride * 12000) === 0) onProgress?.(Math.round(point / header.pointCount * 100))
  }
  onProgress?.(100)
  return { header, positions: new Float32Array(positions), colors: new Float32Array(colors), sourceIndices: new Uint32Array(sourceIndices), renderedPointCount: positions.length / 3 }
}

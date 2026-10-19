import { unzipSync } from 'fflate'
import type { PointCloudData } from '@/lib/las-point-cloud'

export interface NumpyArray {
  dtype: string
  shape: number[]
  data: Uint8Array | Uint32Array | Int32Array | Float32Array | Float64Array
}

function parseShape(value: string): number[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean).map(Number).filter((item) => Number.isFinite(item) && item >= 0)
}

export function parseNpy(bytes: Uint8Array): NumpyArray {
  if (bytes.length < 10 || bytes[0] !== 0x93 || new TextDecoder().decode(bytes.subarray(1, 6)) !== 'NUMPY') throw new Error('NPY 文件头无效')
  const major = bytes[6]
  const headerLength = major === 1
    ? bytes[8] | (bytes[9] << 8)
    : bytes[8] | (bytes[9] << 8) | (bytes[10] << 16) | (bytes[11] << 24)
  const headerOffset = major === 1 ? 10 : 12
  const header = new TextDecoder('latin1').decode(bytes.subarray(headerOffset, headerOffset + headerLength))
  const dtype = /['"]descr['"]\s*:\s*['"]([^'"]+)['"]/.exec(header)?.[1]
  const fortranOrder = /['"]fortran_order['"]\s*:\s*(True|False)/.exec(header)?.[1]
  const shapeText = /['"]shape['"]\s*:\s*\(([^)]*)\)/.exec(header)?.[1]
  if (!dtype || !shapeText) throw new Error('NPY 元数据不完整')
  if (fortranOrder === 'True') throw new Error('暂不支持 Fortran 顺序的 NPY 数组')
  const shape = parseShape(shapeText)
  const count = shape.reduce((total, value) => total * value, 1)
  const payload = bytes.subarray(headerOffset + headerLength)
  const copy = (bytesPerElement: number) => payload.buffer.slice(payload.byteOffset, payload.byteOffset + count * bytesPerElement)
  if (dtype === '|b1' || dtype === '|u1' || dtype === '<u1') return { dtype, shape, data: payload.slice(0, count) }
  if (dtype === '<f4' || dtype === '=f4') return { dtype, shape, data: new Float32Array(copy(4)) }
  if (dtype === '<f8' || dtype === '=f8') return { dtype, shape, data: new Float64Array(copy(8)) }
  if (dtype === '<i4' || dtype === '=i4') return { dtype, shape, data: new Int32Array(copy(4)) }
  if (dtype === '<u4' || dtype === '=u4') return { dtype, shape, data: new Uint32Array(copy(4)) }
  throw new Error(`暂不支持 NPY 数据类型 ${dtype}`)
}

export async function loadNpzArchive(url: string, signal?: AbortSignal): Promise<Record<string, NumpyArray>> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`模型数组读取失败（${response.status}）`)
  const archive = unzipSync(new Uint8Array(await response.arrayBuffer()))
  return Object.fromEntries(Object.entries(archive).filter(([name]) => name.endsWith('.npy')).map(([name, value]) => [name.replace(/\.npy$/i, ''), parseNpy(value)]))
}

export async function loadNpzArray(url: string, preferredName?: string, signal?: AbortSignal): Promise<NumpyArray> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`模型数组读取失败（${response.status}）`)
  const archive = unzipSync(new Uint8Array(await response.arrayBuffer()))
  const entries = Object.entries(archive).filter(([name]) => name.endsWith('.npy'))
  const selected = entries.find(([name]) => name.replace(/\.npy$/i, '').endsWith(preferredName || '')) || entries[0]
  if (!selected) throw new Error('NPZ 中没有可读取的数组')
  return parseNpy(selected[1])
}

export async function loadPointVisualizationPreview(url: string, signal?: AbortSignal): Promise<{
  cloud: PointCloudData
  targetMask: Float32Array
  targetProbabilities: Float32Array
}> {
  const archive = await loadNpzArchive(url, signal)
  const positions = archive.positions?.data
  const colors = archive.colors?.data
  const mask = archive.target_mask?.data
  const probabilities = archive.target_probabilities?.data
  const indices = archive.source_indices?.data
  const bounds = archive.source_bounds?.data
  const sourceCount = Number(archive.num_source_points?.data[0] || 0)
  if (!positions || !colors || !mask || !probabilities || !indices || !bounds || archive.positions.shape.length !== 2 || archive.positions.shape[1] !== 3) throw new Error('点云预览产物结构不完整')
  const renderedCount = archive.positions.shape[0]
  const minX = Number(bounds[0]), minY = Number(bounds[1]), minZ = Number(bounds[2])
  const maxX = Number(bounds[3]), maxY = Number(bounds[4]), maxZ = Number(bounds[5])
  const centerX = (minX + maxX) / 2, centerY = (minY + maxY) / 2, centerZ = (minZ + maxZ) / 2
  const span = Math.max(maxX - minX, maxY - minY, 1)
  const normalized = new Float32Array(renderedCount * 3)
  const normalizedColors = new Float32Array(renderedCount * 3)
  const targetMask = new Float32Array(renderedCount)
  const targetProbabilities = new Float32Array(renderedCount)
  for (let index = 0; index < renderedCount; index += 1) {
    normalized[index * 3] = (Number(positions[index * 3]) - centerX) / span * 2
    normalized[index * 3 + 1] = (Number(positions[index * 3 + 2]) - centerZ) / span * 2
    normalized[index * 3 + 2] = -(Number(positions[index * 3 + 1]) - centerY) / span * 2
    normalizedColors[index * 3] = Number(colors[index * 3]) / 255
    normalizedColors[index * 3 + 1] = Number(colors[index * 3 + 1]) / 255
    normalizedColors[index * 3 + 2] = Number(colors[index * 3 + 2]) / 255
    targetMask[index] = Number(mask[index])
    targetProbabilities[index] = Number(probabilities[index])
  }
  return {
    cloud: {
      header: { version: 'preview', pointDataOffset: 0, pointFormat: 0, pointRecordLength: 0, pointCount: sourceCount, scale: [1, 1, 1], offset: [0, 0, 0], bounds: { minX, minY, minZ, maxX, maxY, maxZ } },
      positions: normalized,
      colors: normalizedColors,
      sourceIndices: new Uint32Array(Array.from(indices, Number)),
      renderedPointCount: renderedCount,
    },
    targetMask,
    targetProbabilities,
  }
}

import { Directory, Filesystem } from '@capacitor/filesystem'
import type { EvidencePhoto, EvidencePhotoKind } from '@/domain/fieldDraft'

const ROOT_DIRECTORY = 'hydroguardian/evidence'

async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

export const evidenceFileService = {
  async savePhoto(
    workorderId: string,
    kind: EvidencePhotoKind,
    base64Data: string,
    format = 'jpeg',
  ): Promise<EvidencePhoto> {
    const safeFormat = format.toLowerCase() === 'png' ? 'png' : 'jpeg'
    const capturedAt = new Date().toISOString()
    const id = `${kind}-${Date.now()}`
    const path = `${ROOT_DIRECTORY}/${workorderId}/${id}.${safeFormat === 'jpeg' ? 'jpg' : 'png'}`

    await Filesystem.writeFile({
      path,
      directory: Directory.Data,
      data: base64Data,
      recursive: true,
    })
    const stat = await Filesystem.stat({ path, directory: Directory.Data })

    return {
      id,
      kind,
      path,
      mimeType: `image/${safeFormat}`,
      sizeBytes: stat.size,
      capturedAt,
    }
  },

  async readPreview(photo: EvidencePhoto): Promise<string> {
    const result = await Filesystem.readFile({
      path: photo.path,
      directory: Directory.Data,
    })
    if (result.data instanceof Blob) return blobToDataUrl(result.data)
    return `data:${photo.mimeType};base64,${result.data}`
  },

  async readAsBlob(photo: EvidencePhoto): Promise<Blob> {
    const result = await Filesystem.readFile({
      path: photo.path,
      directory: Directory.Data,
    })
    if (result.data instanceof Blob) return result.data
    const binary = atob(result.data)
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
    return new Blob([bytes], { type: photo.mimeType })
  },

  async readBase64(photo: EvidencePhoto): Promise<string> {
    const result = await Filesystem.readFile({
      path: photo.path,
      directory: Directory.Data,
    })
    if (result.data instanceof Blob) {
      const dataUrl = await blobToDataUrl(result.data)
      return dataUrl.slice(dataUrl.indexOf(',') + 1)
    }
    return result.data
  },

  async remove(path: string) {
    try {
      await Filesystem.deleteFile({ path, directory: Directory.Data })
    } catch {
      // A missing evidence file is already in the desired state.
    }
  },

  async clearAll() {
    try {
      await Filesystem.rmdir({
        path: ROOT_DIRECTORY,
        directory: Directory.Data,
        recursive: true,
      })
    } catch {
      // The evidence directory may not exist yet.
    }
  },
}

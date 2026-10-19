export type EvidencePhotoKind = 'before' | 'after'

export interface EvidencePhoto {
  id: string
  kind: EvidencePhotoKind
  path: string
  mimeType: string
  sizeBytes: number
  capturedAt: string
}

export interface LocationSnapshot {
  latitude: number
  longitude: number
  accuracy: number
  capturedAt: string
}

export interface FieldDraft {
  workorderId: string
  note: string
  photos: EvidencePhoto[]
  location: LocationSnapshot | null
  updatedAt: string
  submittedAt: string | null
}

export function createFieldDraft(workorderId: string): FieldDraft {
  return {
    workorderId,
    note: '',
    photos: [],
    location: null,
    updatedAt: new Date().toISOString(),
    submittedAt: null,
  }
}

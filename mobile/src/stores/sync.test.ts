import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { Preferences } from '@capacitor/preferences'
import { createFieldDraft } from '@/domain/fieldDraft'
import { fieldWorkOrders } from '@/data/workorders'
import { useSyncStore } from './sync'

describe('sync store', () => {
  beforeEach(async () => {
    await Preferences.clear()
    setActivePinia(createPinia())
  })

  it('persists a field submission record and its evidence count', async () => {
    const draft = createFieldDraft('wo-2004')
    draft.location = {
      latitude: 32.356,
      longitude: 119.223,
      accuracy: 8,
      capturedAt: '2026-07-27T10:30:00+08:00',
    }
    draft.photos = [
      {
        id: 'before-1',
        kind: 'before',
        path: 'evidence/before.jpg',
        mimeType: 'image/jpeg',
        sizeBytes: 1024,
        capturedAt: '2026-07-27T10:31:00+08:00',
      },
      {
        id: 'after-1',
        kind: 'after',
        path: 'evidence/after.jpg',
        mimeType: 'image/jpeg',
        sizeBytes: 1200,
        capturedAt: '2026-07-27T10:35:00+08:00',
      },
    ]

    const firstStore = useSyncStore()
    await firstStore.registerSubmission(fieldWorkOrders[1], draft)

    setActivePinia(createPinia())
    const restoredStore = useSyncStore()
    await restoredStore.hydrate()

    expect(restoredStore.records).toHaveLength(1)
    expect(restoredStore.records[0].assetCount).toBe(2)
    expect(restoredStore.records[0].hasLocation).toBe(true)
    expect(restoredStore.records[0].assets).toEqual([
      expect.objectContaining({ photoId: 'before-1', kind: 'before' }),
      expect.objectContaining({ photoId: 'after-1', kind: 'after' }),
    ])
    expect(restoredStore.records[0].submissionId).toContain('field-feedback-wo-2004')
  })
})

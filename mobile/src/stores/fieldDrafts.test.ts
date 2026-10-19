import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { Preferences } from '@capacitor/preferences'
import { useFieldDraftStore } from './fieldDrafts'

describe('field draft store', () => {
  beforeEach(async () => {
    await Preferences.clear()
    setActivePinia(createPinia())
  })

  it('restores notes and GPS metadata after the store is recreated', async () => {
    const firstStore = useFieldDraftStore()
    await firstStore.updateNote('wo-2004', '已完成临水坡面加固和警示标识设置')
    await firstStore.setLocation('wo-2004', {
      latitude: 32.356,
      longitude: 119.223,
      accuracy: 8,
      capturedAt: '2026-07-27T10:30:00+08:00',
    })

    setActivePinia(createPinia())
    const restoredStore = useFieldDraftStore()
    await restoredStore.hydrate()

    expect(restoredStore.getByWorkorderId('wo-2004')?.note).toContain('坡面加固')
    expect(restoredStore.getByWorkorderId('wo-2004')?.location?.accuracy).toBe(8)
  })
})

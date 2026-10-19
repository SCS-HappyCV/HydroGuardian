import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { Preferences } from '@capacitor/preferences'
import { useWorkorderStore } from './workorders'

describe('workorder store', () => {
  beforeEach(async () => {
    await Preferences.clear()
    setActivePinia(createPinia())
  })

  it('groups workorders by their workflow status', () => {
    const store = useWorkorderStore()

    expect(store.activeCount).toBe(2)
    expect(store.reviewedCount).toBe(0)
    expect(store.closedCount).toBe(1)
  })

  it('moves a submitted workorder into review', async () => {
    const store = useWorkorderStore()

    await store.setStatus('wo-2004', 'reviewed')

    expect(store.getById('wo-2004')?.status).toBe('reviewed')
    expect(store.activeCount).toBe(1)
    expect(store.reviewedCount).toBe(1)
  })

  it('restores saved workflow state after the store is recreated', async () => {
    const firstStore = useWorkorderStore()
    await firstStore.setStatus('wo-2001', 'in_progress')

    setActivePinia(createPinia())
    const restoredStore = useWorkorderStore()
    await restoredStore.hydrate()

    expect(restoredStore.getById('wo-2001')?.status).toBe('in_progress')
  })
})

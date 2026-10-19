import { Preferences } from '@capacitor/preferences'
import type { SyncRecord } from '@/domain/sync'

const STORAGE_KEY = 'hydroguardian.sync-records.v1'

export const syncRepository = {
  async loadAll(): Promise<SyncRecord[]> {
    const { value } = await Preferences.get({ key: STORAGE_KEY })
    if (!value) return []

    try {
      const data: unknown = JSON.parse(value)
      return Array.isArray(data) ? data as SyncRecord[] : []
    } catch {
      return []
    }
  },

  async saveAll(records: SyncRecord[]) {
    await Preferences.set({
      key: STORAGE_KEY,
      value: JSON.stringify(records),
    })
  },

  async clear() {
    await Preferences.remove({ key: STORAGE_KEY })
  },
}

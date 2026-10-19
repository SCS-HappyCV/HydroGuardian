import { Preferences } from '@capacitor/preferences'
import type { FieldDraft } from '@/domain/fieldDraft'

const STORAGE_KEY = 'hydroguardian.field-drafts.v1'

export const fieldDraftRepository = {
  async loadAll(): Promise<FieldDraft[]> {
    const { value } = await Preferences.get({ key: STORAGE_KEY })
    if (!value) return []

    try {
      const data: unknown = JSON.parse(value)
      return Array.isArray(data) ? data as FieldDraft[] : []
    } catch {
      return []
    }
  },

  async saveAll(drafts: FieldDraft[]) {
    await Preferences.set({
      key: STORAGE_KEY,
      value: JSON.stringify(drafts),
    })
  },

  async clear() {
    await Preferences.remove({ key: STORAGE_KEY })
  },
}

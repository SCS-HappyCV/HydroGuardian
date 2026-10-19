import { Preferences } from '@capacitor/preferences'
import type { MobileWorkOrder } from '@/domain/workorder'

const STORAGE_KEY = 'hydroguardian.workorders.v1'

function clone(items: MobileWorkOrder[]) {
  return items.map((item) => ({
    ...item,
    evidence: item.evidence.map((evidence) => ({ ...evidence })),
  }))
}

export const workorderRepository = {
  async load(): Promise<MobileWorkOrder[] | null> {
    const { value } = await Preferences.get({ key: STORAGE_KEY })
    if (!value) return null

    try {
      const data: unknown = JSON.parse(value)
      return Array.isArray(data) ? clone(data as MobileWorkOrder[]) : null
    } catch {
      return null
    }
  },

  async save(items: MobileWorkOrder[]) {
    await Preferences.set({
      key: STORAGE_KEY,
      value: JSON.stringify(items),
    })
  },

  async clear() {
    await Preferences.remove({ key: STORAGE_KEY })
  },
}

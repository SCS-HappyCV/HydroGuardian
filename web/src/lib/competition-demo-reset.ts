import { setPresentationMode } from '@/lib/presentation-mode'
import { savePersistedDataMode } from '@/lib/runtime-mode'

const DEMO_STORAGE_PREFIX = 'hydroguardian_'

export function resetCompetitionDemoState(): void {
  if (typeof window === 'undefined') return

  const keysToRemove: string[] = []
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index)
    if (key?.startsWith(DEMO_STORAGE_PREFIX)) keysToRemove.push(key)
  }

  keysToRemove.forEach((key) => window.localStorage.removeItem(key))
  setPresentationMode('operations')
  savePersistedDataMode('mock')
}

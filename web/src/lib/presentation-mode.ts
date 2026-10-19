import { computed, ref } from 'vue'

export type PresentationMode = 'competition' | 'operations'

const STORAGE_KEY = 'hydroguardian_presentation_mode'
const defaultMode: PresentationMode = 'operations'
const presentationMode = ref<PresentationMode>(defaultMode)
let initialized = false

export function isPresentationMode(value: string | null | undefined): value is PresentationMode {
  return value === 'competition' || value === 'operations'
}

export function initializePresentationMode(): PresentationMode {
  if (initialized || typeof window === 'undefined') return presentationMode.value

  const persisted = window.localStorage.getItem(STORAGE_KEY)
  presentationMode.value = persisted === 'operations' ? persisted : defaultMode
  if (persisted !== presentationMode.value) window.localStorage.setItem(STORAGE_KEY, presentationMode.value)
  initialized = true
  return presentationMode.value
}

export function setPresentationMode(mode: PresentationMode): void {
  presentationMode.value = mode
  if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, mode)
}

export function togglePresentationMode(): PresentationMode {
  const nextMode = presentationMode.value === 'competition' ? 'operations' : 'competition'
  setPresentationMode(nextMode)
  return nextMode
}

export function usePresentationMode() {
  return {
    mode: presentationMode,
    isCompetitionMode: computed(() => presentationMode.value === 'competition'),
    initializePresentationMode,
    setPresentationMode,
    togglePresentationMode,
  }
}

import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { Preferences } from '@capacitor/preferences'
import { useSessionStore } from './session'

describe('session store', () => {
  beforeEach(async () => {
    await Preferences.clear()
    setActivePinia(createPinia())
  })

  it('remembers the field identity between application sessions', async () => {
    const firstSession = useSessionStore()
    await firstSession.enter()

    setActivePinia(createPinia())
    const restoredSession = useSessionStore()
    await restoredSession.initialize()

    expect(restoredSession.isAuthenticated).toBe(true)
    expect(restoredSession.currentUser?.name).toBe('许然')
  })

  it('clears the active identity when signing out', async () => {
    const session = useSessionStore()
    await session.enter()
    await session.signOut()

    expect(session.isAuthenticated).toBe(false)
  })
})

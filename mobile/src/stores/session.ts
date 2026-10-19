import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { Preferences } from '@capacitor/preferences'
import { primaryFieldUser, type FieldUser } from '@/domain/user'

const SESSION_KEY = 'hydroguardian.session.v1'

export const useSessionStore = defineStore('session', () => {
  const initialized = ref(false)
  const currentUser = ref<FieldUser | null>(null)
  const isAuthenticated = computed(() => currentUser.value !== null)

  async function initialize() {
    if (initialized.value) return
    const { value } = await Preferences.get({ key: SESSION_KEY })

    if (value) {
      try {
        currentUser.value = JSON.parse(value) as FieldUser
      } catch {
        await Preferences.remove({ key: SESSION_KEY })
      }
    }

    initialized.value = true
  }

  async function enter() {
    currentUser.value = { ...primaryFieldUser }
    await Preferences.set({
      key: SESSION_KEY,
      value: JSON.stringify(currentUser.value),
    })
  }

  async function signOut() {
    currentUser.value = null
    await Preferences.remove({ key: SESSION_KEY })
  }

  return {
    initialized,
    currentUser,
    isAuthenticated,
    initialize,
    enter,
    signOut,
  }
})

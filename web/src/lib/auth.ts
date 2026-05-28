import { computed, ref } from 'vue'
import type { AuthUser } from '@/lib/api-contracts'

export type { AuthUser }

interface AuthSession {
  token: string
  user: AuthUser
}

const AUTH_TOKEN_KEY = 'auth_token'
const AUTH_USER_KEY = 'auth_user'

const authToken = ref('')
const authUser = ref<AuthUser | null>(null)
const initialized = ref(false)
let hasStorageListener = false

const isLoggedIn = computed(() => Boolean(authToken.value && authUser.value))

function parseAuthUser(raw: string | null): AuthUser | null {
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as AuthUser
    if (!parsed?.id || !parsed?.name || !parsed?.email) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

function persistSession() {
  if (typeof window === 'undefined') return

  if (authToken.value && authUser.value) {
    localStorage.setItem(AUTH_TOKEN_KEY, authToken.value)
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(authUser.value))
    return
  }

  localStorage.removeItem(AUTH_TOKEN_KEY)
  localStorage.removeItem(AUTH_USER_KEY)
}

function loadAuthState() {
  if (typeof window === 'undefined') return

  const token = localStorage.getItem(AUTH_TOKEN_KEY) ?? ''
  const user = parseAuthUser(localStorage.getItem(AUTH_USER_KEY))

  if (token && user) {
    authToken.value = token
    authUser.value = user
  } else {
    authToken.value = ''
    authUser.value = null
  }

  initialized.value = true
}

function bindStorageListener() {
  if (typeof window === 'undefined' || hasStorageListener) return

  hasStorageListener = true
  window.addEventListener('storage', (event) => {
    if (event.key === AUTH_TOKEN_KEY || event.key === AUTH_USER_KEY) {
      loadAuthState()
    }
  })
}

export function setAuthSession(session: AuthSession) {
  authToken.value = session.token
  authUser.value = session.user
  persistSession()
}

export function clearAuthSession() {
  authToken.value = ''
  authUser.value = null
  persistSession()
}

export function useAuthState() {
  if (!initialized.value) {
    loadAuthState()
  }

  bindStorageListener()

  return {
    authToken,
    authUser,
    isLoggedIn,
    loadAuthState
  }
}

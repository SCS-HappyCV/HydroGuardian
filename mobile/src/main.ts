import { createApp } from 'vue'
import { App as CapacitorApp } from '@capacitor/app'
import { IonicVue } from '@ionic/vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { taskDetailPath } from '@/router/paths'
import { useSessionStore } from '@/stores/session'
import { useFieldDraftStore } from '@/stores/fieldDrafts'
import { useSyncStore } from '@/stores/sync'
import { useWorkorderStore } from '@/stores/workorders'

import '@ionic/vue/css/core.css'
import '@ionic/vue/css/normalize.css'
import '@ionic/vue/css/structure.css'
import '@ionic/vue/css/typography.css'
import '@ionic/vue/css/padding.css'
import '@ionic/vue/css/float-elements.css'
import '@ionic/vue/css/text-alignment.css'
import '@ionic/vue/css/text-transformation.css'
import '@ionic/vue/css/flex-utils.css'
import '@ionic/vue/css/display.css'
import './theme/variables.css'
import './theme/app.css'

const pinia = createPinia()
const app = createApp(App)
  .use(IonicVue)
  .use(pinia)
  .use(router)

const session = useSessionStore(pinia)
const workorders = useWorkorderStore(pinia)
const fieldDrafts = useFieldDraftStore(pinia)
const syncStore = useSyncStore(pinia)

router.beforeEach(async (to) => {
  await session.initialize()
  if (to.meta.requiresAuth && !session.isAuthenticated) {
    return { path: '/welcome', query: { redirect: to.fullPath } }
  }
  if (to.path === '/welcome' && session.isAuthenticated) {
    return typeof to.query.redirect === 'string' ? to.query.redirect : '/tabs/tasks'
  }
})

Promise.all([
  session.initialize(),
  fieldDrafts.hydrate(),
  syncStore.hydrate(),
])
  .then(() => router.isReady())
  .then(() => {
    app.mount('#app')
    void workorders.hydrate()
  })

void CapacitorApp.addListener('appUrlOpen', ({ url }) => {
  try {
    const target = new URL(url)
    if (target.protocol !== 'hydroguardian:' || target.hostname !== 'task') return
    const workorderId = target.pathname.replace(/^\/+/, '')
    if (workorderId) void router.push(taskDetailPath(workorderId))
  } catch {
    // Ignore unrelated or malformed application links.
  }
})

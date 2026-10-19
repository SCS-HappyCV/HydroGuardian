import { createRouter, createWebHistory } from '@ionic/vue-router'
import type { RouteRecordRaw } from 'vue-router'
import TabsPage from '@/views/TabsPage.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/welcome' },
  {
    path: '/welcome',
    name: 'welcome',
    component: () => import('@/views/WelcomePage.vue'),
  },
  {
    path: '/tabs',
    component: TabsPage,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/tabs/tasks' },
      { path: 'tasks', component: () => import('@/views/TaskListPage.vue') },
      { path: 'tasks/:id', component: () => import('@/views/TaskDetailPage.vue') },
      { path: 'tasks/:id/feedback', component: () => import('@/views/FieldFeedbackPage.vue') },
      { path: 'map', component: () => import('@/views/MapPage.vue') },
      { path: 'sync', component: () => import('@/views/SyncPage.vue') },
      { path: 'profile', component: () => import('@/views/ProfilePage.vue') },
      { path: 'profile/device-check', component: () => import('@/views/DeviceCheckPage.vue') },
      { path: 'profile/privacy', component: () => import('@/views/PrivacyPage.vue') },
    ],
  },
  {
    path: '/tasks/:id/feedback',
    redirect: (to) => `/tabs/tasks/${encodeURIComponent(String(to.params.id))}/feedback`,
  },
  {
    path: '/tasks/:id',
    redirect: (to) => `/tabs/tasks/${encodeURIComponent(String(to.params.id))}`,
  },
]

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

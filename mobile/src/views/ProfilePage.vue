<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { IonAlert, IonContent, IonIcon, IonPage, IonToggle } from '@ionic/vue'
import {
  chevronForwardOutline,
  informationCircleOutline,
  logOutOutline,
  notificationsOutline,
  phonePortraitOutline,
  refreshOutline,
  shieldCheckmarkOutline,
} from 'ionicons/icons'
import MobileHeader from '@/components/MobileHeader.vue'
import { useSessionStore } from '@/stores/session'
import { useFieldDraftStore } from '@/stores/fieldDrafts'
import { useSyncStore } from '@/stores/sync'
import { useWorkorderStore } from '@/stores/workorders'

const router = useRouter()
const session = useSessionStore()
const workorders = useWorkorderStore()
const drafts = useFieldDraftStore()
const syncStore = useSyncStore()
const showResetAlert = ref(false)
const showSignOutAlert = ref(false)
const notificationsEnabled = ref(true)
const inProgressCount = computed(() => workorders.items.filter((item) => item.status === 'in_progress').length)

async function handleResetDismiss(event: CustomEvent<{ role?: string }>) {
  showResetAlert.value = false
  if (event.detail.role === 'confirm') {
    await Promise.all([
      workorders.resetAll(),
      drafts.clearAll(),
      syncStore.clearAll(),
    ])
    await router.replace('/tabs/tasks')
  }
}

async function handleSignOutDismiss(event: CustomEvent<{ role?: string }>) {
  showSignOutAlert.value = false
  if (event.detail.role !== 'confirm') return
  await session.signOut()
  await router.replace('/welcome')
}
</script>

<template>
  <IonPage>
    <MobileHeader title="我的" subtitle="现场巡检账号与应用设置" />
    <IonContent>
      <div class="page-shell profile-shell">
        <section class="identity surface">
          <div class="avatar">{{ session.currentUser?.name.slice(0, 1) }}</div>
          <div><h2>{{ session.currentUser?.name }}</h2><p>{{ session.currentUser?.role }} · {{ session.currentUser?.region }}</p></div>
          <span>在线</span>
        </section>
        <section class="today surface">
          <div><strong>{{ workorders.activeCount }}</strong><span>今日任务</span></div>
          <div><strong>{{ inProgressCount }}</strong><span>处理中</span></div>
          <div><strong>{{ workorders.closedCount }}</strong><span>本月闭环</span></div>
        </section>
        <section class="settings surface">
          <div><IonIcon :icon="notificationsOutline" /><span>任务通知</span><IonToggle v-model="notificationsEnabled" /></div>
          <button type="button" @click="router.push('/tabs/profile/device-check')"><IonIcon :icon="phonePortraitOutline" /><span>设备能力检查</span><IonIcon :icon="chevronForwardOutline" /></button>
          <button type="button" @click="router.push('/tabs/profile/privacy')"><IonIcon :icon="shieldCheckmarkOutline" /><span>权限与数据安全</span><IonIcon :icon="chevronForwardOutline" /></button>
          <button type="button" @click="showResetAlert = true"><IonIcon :icon="refreshOutline" /><span>恢复初始任务数据</span><IonIcon :icon="chevronForwardOutline" /></button>
          <div><IonIcon :icon="informationCircleOutline" /><span>关于水利智巡</span><small>v1.0.0</small></div>
          <button type="button" class="sign-out" @click="showSignOutAlert = true"><IonIcon :icon="logOutOutline" /><span>退出当前身份</span><IonIcon :icon="chevronForwardOutline" /></button>
        </section>
      </div>
    </IonContent>
    <IonAlert
      :is-open="showResetAlert"
      header="恢复初始数据"
      message="任务状态和现场操作记录将恢复到初始状态。"
      :buttons="[
        { text: '取消', role: 'cancel' },
        { text: '确认恢复', role: 'confirm' },
      ]"
      @did-dismiss="handleResetDismiss"
    />
    <IonAlert
      :is-open="showSignOutAlert"
      header="退出当前身份"
      message="下次打开应用时需要重新进入工作台。"
      :buttons="[
        { text: '取消', role: 'cancel' },
        { text: '确认退出', role: 'confirm' },
      ]"
      @did-dismiss="handleSignOutDismiss"
    />
  </IonPage>
</template>

<style scoped>
.profile-shell { display: grid; gap: 13px; }
.identity { display: grid; grid-template-columns: 52px 1fr auto; align-items: center; gap: 12px; padding: 16px; }
.avatar { display: grid; width: 52px; height: 52px; place-items: center; border: 1px solid rgba(45,212,191,.2); border-radius: 17px; background: linear-gradient(145deg, #164559, #193a4c); color: #8aebef; font-size: 20px; font-weight: 800; }
.identity h2 { margin: 0; font-size: 16px; }
.identity p { margin: 5px 0 0; color: #71849a; font-size: 9px; }
.identity > span { border-radius: 999px; background: rgba(57,201,138,.09); padding: 5px 8px; color: #63e3af; font-size: 9px; }
.today { display: grid; grid-template-columns: repeat(3, 1fr); padding: 14px; }
.today div { text-align: center; }
.today div + div { border-left: 1px solid rgba(148,180,208,.09); }
.today strong, .today span { display: block; }
.today strong { font-size: 19px; }
.today span { margin-top: 4px; color: #71849a; font-size: 9px; }
.settings { padding: 0 14px; }
.settings > div,
.settings > button { display: grid; width: 100%; grid-template-columns: 24px 1fr auto; align-items: center; min-height: 54px; border: 0; padding: 0; color: #9bb0c5; background: transparent; text-align: left; }
.settings > * + * { border-top: 1px solid rgba(148,180,208,.08); }
.settings > * > ion-icon:first-child { color: #55d8df; font-size: 18px; }
.settings span { color: #dce8f3; font-size: 11px; }
.settings small { color: #71849a; font-size: 9px; }
.settings .sign-out ion-icon:first-child,
.settings .sign-out span { color: #ff837c; }
</style>

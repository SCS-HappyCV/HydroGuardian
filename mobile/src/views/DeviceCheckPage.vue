<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonIcon,
  IonPage,
  IonSpinner,
  IonTitle,
  IonToolbar,
} from '@ionic/vue'
import {
  alertCircleOutline,
  cameraOutline,
  checkmarkCircleOutline,
  cloudOutline,
  folderOpenOutline,
  locationOutline,
  refreshOutline,
  timeOutline,
} from 'ionicons/icons'
import { deviceReadinessService, type ReadinessItem } from '@/services/deviceReadinessService'

const items = ref<ReadinessItem[]>([])
const checking = ref(false)
const allReady = computed(() => items.value.length > 0 && items.value.every((item) => item.state !== 'attention'))

const icons = {
  camera: cameraOutline,
  location: locationOutline,
  storage: folderOpenOutline,
  network: cloudOutline,
}

async function runCheck() {
  checking.value = true
  items.value = await deviceReadinessService.check()
  checking.value = false
}

onMounted(runCheck)
</script>

<template>
  <IonPage>
    <IonHeader class="ion-no-border">
      <IonToolbar>
        <IonButtons slot="start">
          <IonBackButton default-href="/tabs/profile" text="" />
        </IonButtons>
        <IonTitle>设备能力检查</IonTitle>
      </IonToolbar>
    </IonHeader>
    <IonContent>
      <main class="page-shell check-page">
        <section class="check-hero surface" :class="{ attention: !allReady && items.length }">
          <div>
            <IonSpinner v-if="checking" name="crescent" />
            <IonIcon v-else :icon="allReady ? checkmarkCircleOutline : alertCircleOutline" />
          </div>
          <h1>{{ checking ? '正在检查设备能力' : allReady ? '现场作业能力可用' : '有项目需要处理' }}</h1>
          <p>检查不会主动申请权限；相机和定位将在实际使用时请求。</p>
        </section>

        <section class="check-list surface">
          <article v-for="item in items" :key="item.id">
            <span class="capability-icon"><IonIcon :icon="icons[item.id]" /></span>
            <div><strong>{{ item.label }}</strong><p>{{ item.detail }}</p></div>
            <span class="state" :class="item.state">
              <IonIcon :icon="item.state === 'ready' ? checkmarkCircleOutline : item.state === 'prompt' ? timeOutline : alertCircleOutline" />
              {{ item.state === 'ready' ? '正常' : item.state === 'prompt' ? '使用时确认' : '需处理' }}
            </span>
          </article>
        </section>

        <IonButton expand="block" fill="outline" :disabled="checking" @click="runCheck">
          <IonIcon slot="start" :icon="refreshOutline" />重新检查
        </IonButton>
      </main>
    </IonContent>
  </IonPage>
</template>

<style scoped>
.check-page { display: grid; gap: 14px; }
.check-hero { padding: 25px 18px; text-align: center; }
.check-hero > div { display: grid; width: 58px; height: 58px; margin: 0 auto; place-items: center; border-radius: 18px; color: #63e3af; background: rgba(57,201,138,.09); font-size: 31px; }
.check-hero.attention > div { color: #ffd06b; background: rgba(245,185,66,.09); }
.check-hero ion-spinner { width: 25px; }
.check-hero h1 { margin: 13px 0 0; font-size: 17px; }
.check-hero p { margin: 6px auto 0; max-width: 330px; color: #71849a; font-size: 9px; line-height: 1.6; }
.check-list { padding: 0 14px; }
.check-list article { display: grid; grid-template-columns: 38px 1fr auto; align-items: center; gap: 10px; padding: 14px 0; }
.check-list article + article { border-top: 1px solid rgba(148,180,208,.08); }
.capability-icon { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 12px; color: #55d8df; background: rgba(45,212,191,.08); font-size: 19px; }
.check-list strong { font-size: 11px; }
.check-list p { margin: 4px 0 0; color: #71849a; font-size: 8px; line-height: 1.5; }
.state { display: flex; align-items: center; gap: 3px; color: #ff837c; font-size: 8px; }
.state.ready { color: #63e3af; }
.state.prompt { color: #ffd06b; }
.check-page > ion-button { min-height: 44px; margin: 0; font-size: 10px; --border-radius: 13px; }
</style>

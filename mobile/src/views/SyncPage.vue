<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import {
  IonButton,
  IonContent,
  IonIcon,
  IonPage,
  IonSpinner,
} from '@ionic/vue'
import {
  alertCircleOutline,
  checkmarkCircleOutline,
  cloudDoneOutline,
  cloudUploadOutline,
  documentTextOutline,
  imagesOutline,
  locationOutline,
  refreshOutline,
  timeOutline,
} from 'ionicons/icons'
import MobileHeader from '@/components/MobileHeader.vue'
import { syncStatusLabels } from '@/domain/sync'
import { taskDetailPath } from '@/router/paths'
import { useSyncStore } from '@/stores/sync'

const router = useRouter()
const store = useSyncStore()
const {
  records,
  isConnected,
  pendingCount,
  failedCount,
  syncedCount,
  photoCount,
  latestSyncAt,
} = storeToRefs(store)
const retryingId = ref('')
const feedbackMessage = ref('')

const heroTitle = computed(() => {
  if (records.value.some((item) => item.status === 'uploading')) return '正在上传现场证据'
  if (records.value.some((item) => item.status === 'conflict')) return '工单状态需要确认'
  if (failedCount.value) return `${failedCount.value} 条记录需要处理`
  if (pendingCount.value) return `${pendingCount.value} 条记录等待提交`
  if (records.value.length) return '全部记录已提交'
  return '等待现场记录'
})

const heroCaption = computed(() => {
  if (!isConnected.value) return '连接恢复后可重新提交'
  if (latestSyncAt.value) {
    return `最近提交 ${new Date(latestSyncAt.value).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })}`
  }
  return '完成现场处置后，记录会显示在这里'
})

async function retryRecord(recordId: string) {
  retryingId.value = recordId
  const succeeded = await store.retry(recordId)
  feedbackMessage.value = succeeded ? '记录已重新提交' : '当前连接不可用，请稍后重试'
  retryingId.value = ''
}

async function retryAll() {
  retryingId.value = 'all'
  const succeeded = await store.retryAll()
  feedbackMessage.value = succeeded ? '全部记录已提交' : '仍有记录未能提交'
  retryingId.value = ''
}
</script>

<template>
  <IonPage>
    <MobileHeader title="数据同步" subtitle="现场记录与证据状态">
      <template #action>
        <span class="network-state" :class="{ disconnected: !isConnected }">
          <i />{{ isConnected ? '连接正常' : '等待连接' }}
        </span>
      </template>
    </MobileHeader>
    <IonContent>
      <div class="page-shell sync-shell">
        <section class="sync-hero surface" :class="{ attention: failedCount || pendingCount }">
          <div class="cloud">
            <IonIcon :icon="failedCount ? alertCircleOutline : pendingCount ? cloudUploadOutline : cloudDoneOutline" />
          </div>
          <h2>{{ heroTitle }}</h2>
          <p>{{ heroCaption }}</p>
          <IonButton
            v-if="failedCount || pendingCount"
            size="small"
            fill="outline"
            :disabled="retryingId === 'all'"
            @click="retryAll"
          >
            <IonSpinner v-if="retryingId === 'all'" name="crescent" />
            <template v-else><IonIcon slot="start" :icon="refreshOutline" />全部重试</template>
          </IonButton>
          <span v-if="feedbackMessage" class="feedback">{{ feedbackMessage }}</span>
        </section>

        <section class="stats surface">
          <div><IonIcon :icon="imagesOutline" /><span>现场影像</span><strong>{{ photoCount }}</strong></div>
          <div><IonIcon :icon="documentTextOutline" /><span>处置记录</span><strong>{{ records.length }}</strong></div>
          <div><IonIcon :icon="checkmarkCircleOutline" /><span>完成提交</span><strong>{{ syncedCount }}</strong></div>
        </section>

        <div class="section-label">最近记录</div>
        <section v-if="records.length" class="records surface">
          <article v-for="record in records" :key="record.id">
            <span class="record-icon" :class="record.status">
              <IonIcon :icon="record.status === 'synced' ? checkmarkCircleOutline : record.status === 'failed' ? alertCircleOutline : timeOutline" />
            </span>
            <button type="button" class="record-main" @click="router.push(taskDetailPath(record.workorderId))">
              <strong>{{ record.title }}</strong>
              <small>
                {{ record.assetCount }} 张影像
                <template v-if="record.hasLocation"> · <IonIcon :icon="locationOutline" />已定位</template>
              </small>
              <small v-if="record.lastError" class="record-error">{{ record.lastError }}</small>
              <small v-if="record.assets?.length" class="asset-progress">
                已上传 {{ record.assets.filter((item) => item.status === 'uploaded').length }}/{{ record.assets.length }} 项证据
              </small>
            </button>
            <div class="record-state">
              <span :class="record.status">{{ syncStatusLabels[record.status] }}</span>
              <time>{{ new Date(record.updatedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time>
              <button
                v-if="record.status !== 'synced'"
                type="button"
                :disabled="retryingId === record.id"
                @click="retryRecord(record.id)"
              >
                {{ retryingId === record.id ? '提交中' : '重试' }}
              </button>
            </div>
          </article>
        </section>
        <section v-else class="empty-records surface">
          <IonIcon :icon="documentTextOutline" />
          <strong>暂无现场提交记录</strong>
          <span>完成工单处置后会自动生成记录</span>
        </section>
      </div>
    </IonContent>
  </IonPage>
</template>

<style scoped>
.sync-shell { display: grid; gap: 13px; }
.network-state { display: flex; align-items: center; gap: 5px; border-radius: 999px; padding: 6px 8px; color: #63e3af; background: rgba(57,201,138,.08); font-size: 8px; }
.network-state i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 7px currentColor; }
.network-state.disconnected { color: #ffd06b; background: rgba(245,185,66,.08); }
.sync-hero { padding: 25px; text-align: center; }
.cloud { display: grid; width: 58px; height: 58px; margin: 0 auto; place-items: center; border-radius: 18px; color: #55d8df; background: rgba(45,212,191,.1); font-size: 31px; }
.attention .cloud { color: #ffd06b; background: rgba(245,185,66,.09); }
.sync-hero h2 { margin: 13px 0 0; font-size: 17px; }
.sync-hero p { margin: 5px 0 0; color: #71849a; font-size: 10px; }
.sync-hero ion-button { margin-top: 12px; font-size: 9px; }
.sync-hero ion-spinner { width: 16px; }
.feedback { display: block; margin-top: 7px; color: #9bb0c5; font-size: 9px; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); padding: 14px 6px; }
.stats div { text-align: center; }
.stats div + div { border-left: 1px solid rgba(148,180,208,.1); }
.stats ion-icon { color: #55d8df; font-size: 17px; }
.stats span, .stats strong { display: block; }
.stats span { margin-top: 5px; color: #71849a; font-size: 9px; }
.stats strong { margin-top: 4px; font-size: 17px; }
.section-label { margin: 5px 2px -3px; color: #71849a; font-size: 10px; }
.records { padding: 0 13px; }
.records article { display: grid; grid-template-columns: 30px 1fr auto; align-items: center; gap: 9px; padding: 13px 0; }
.records article + article { border-top: 1px solid rgba(148,180,208,.08); }
.record-icon { display: grid; width: 29px; height: 29px; place-items: center; border-radius: 9px; color: #ffd06b; background: rgba(245,185,66,.09); }
.record-icon.synced { color: #63e3af; background: rgba(57,201,138,.09); }
.record-icon.uploading { color: #55d8df; background: rgba(85,216,223,.09); }
.record-icon.conflict { color: #b8adff; background: rgba(139,124,255,.1); }
.record-icon.failed { color: #ff837c; background: rgba(255,93,93,.09); }
.record-main { min-width: 0; border: 0; padding: 0; color: inherit; background: transparent; text-align: left; }
.record-main strong, .record-main small { display: block; }
.record-main strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.record-main small { display: flex; align-items: center; gap: 2px; margin-top: 4px; color: #71849a; font-size: 8px; }
.record-main .record-error { display: block; overflow: hidden; max-width: 190px; color: #ff9a94; text-overflow: ellipsis; white-space: nowrap; }
.record-main .asset-progress { color: #55d8df; }
.record-state { display: flex; align-items: flex-end; flex-direction: column; gap: 3px; }
.record-state span { color: #ffd06b; font-size: 8px; }
.record-state span.synced { color: #63e3af; }
.record-state span.uploading { color: #55d8df; }
.record-state span.conflict { color: #b8adff; }
.record-state span.failed { color: #ff837c; }
.record-state time { color: #63778d; font-size: 8px; }
.record-state button { border: 0; padding: 3px 0 0; color: #55d8df; background: transparent; font-size: 8px; }
.empty-records { display: flex; align-items: center; flex-direction: column; padding: 35px 20px; color: #71849a; }
.empty-records ion-icon { color: #55d8df; font-size: 27px; }
.empty-records strong { margin-top: 9px; color: #9bb0c5; font-size: 12px; }
.empty-records span { margin-top: 5px; font-size: 9px; }
</style>

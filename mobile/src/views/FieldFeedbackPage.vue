<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera'
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonContent,
  IonFooter,
  IonHeader,
  IonIcon,
  IonPage,
  IonSpinner,
  IonTextarea,
  IonTitle,
  IonToolbar,
  useIonRouter,
} from '@ionic/vue'
import {
  cameraOutline,
  checkmarkCircleOutline,
  cloudDoneOutline,
  locateOutline,
  locationOutline,
  timeOutline,
} from 'ionicons/icons'
import type { EvidencePhotoKind } from '@/domain/fieldDraft'
import { taskDetailPath } from '@/router/paths'
import { evidenceFileService } from '@/services/evidenceFileService'
import { LocationCaptureError, locationService } from '@/services/locationService'
import { useFieldDraftStore } from '@/stores/fieldDrafts'
import { useSyncStore } from '@/stores/sync'
import { useWorkorderStore } from '@/stores/workorders'

const route = useRoute()
const ionRouter = useIonRouter()
const workorders = useWorkorderStore()
const drafts = useFieldDraftStore()
const syncStore = useSyncStore()
const workorderId = String(route.params.id)

const note = ref('')
const photoPreview = ref('')
const ready = ref(false)
const capturing = ref<EvidencePhotoKind | null>(null)
const locating = ref(false)
const captureError = ref('')
const locationError = ref('')
const validationMessage = ref('')
const submissionState = ref<'idle' | 'saving' | 'uploading' | 'synced' | 'failed'>('idle')
const submissionError = ref('')
let noteSaveTimer: number | undefined

const workorder = computed(() => workorders.getById(workorderId))
const draft = computed(() => drafts.getByWorkorderId(workorderId))
const fieldPhoto = computed(() => draft.value?.photos.find((photo) => photo.kind === 'after')
  || draft.value?.photos.find((photo) => photo.kind === 'before'))

const missingItems = computed(() => {
  const missing: string[] = []
  if (!fieldPhoto.value) missing.push('现场影像')
  if (!draft.value?.location) missing.push('现场定位')
  if (note.value.trim().length < 6) missing.push('处置说明')
  return missing
})
const canSubmit = computed(() => missingItems.value.length === 0)

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatSize(value: number) {
  return value >= 1024 * 1024
    ? `${(value / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(value / 1024))} KB`
}

async function restoreDraft() {
  await drafts.hydrate()
  const current = drafts.ensure(workorderId)
  const retainedPhoto = current.photos.find((photo) => photo.kind === 'after') || current.photos[0]
  if (retainedPhoto && current.photos.length > 1) await drafts.retainSinglePhoto(workorderId, retainedPhoto.id)
  note.value = current.note

  await Promise.all((retainedPhoto ? [retainedPhoto] : []).map(async (photo) => {
    try {
      const preview = await evidenceFileService.readPreview(photo)
      if (!photoPreview.value || photo.kind === 'after') photoPreview.value = preview
    } catch {
      captureError.value = '部分历史影像无法读取，请重新采集'
    }
  }))
  ready.value = true
}

async function capturePhoto(kind: EvidencePhotoKind) {
  captureError.value = ''
  validationMessage.value = ''
  capturing.value = kind
  try {
    const result = await Camera.getPhoto({
      quality: 82,
      resultType: CameraResultType.Base64,
      source: CameraSource.Prompt,
      width: 1280,
      correctOrientation: true,
    })
    if (!result.base64String) throw new Error('missing camera data')

    const photo = await evidenceFileService.savePhoto(
      workorderId,
      kind,
      result.base64String,
      result.format,
    )
    await drafts.setSinglePhoto(workorderId, photo)
    const preview = `data:${photo.mimeType};base64,${result.base64String}`
    photoPreview.value = preview
  } catch (error) {
    const message = error instanceof Error ? error.message.toLowerCase() : ''
    if (!message.includes('cancel')) captureError.value = '影像保存失败，请重新拍摄或选择照片'
  } finally {
    capturing.value = null
  }
}

async function captureLocation() {
  locating.value = true
  locationError.value = ''
  validationMessage.value = ''
  try {
    const location = await locationService.capture()
    await drafts.setLocation(workorderId, location)
  } catch (error) {
    locationError.value = error instanceof LocationCaptureError
      ? error.message
      : '定位失败，请稍后重试'
  } finally {
    locating.value = false
  }
}

async function submitFeedback() {
  if (!workorder.value) return
  if (missingItems.value.length) {
    validationMessage.value = `还需补充：${missingItems.value.join('、')}`
    return
  }

  submissionState.value = 'saving'
  submissionError.value = ''
  await drafts.updateNote(workorderId, note.value.trim())
  await drafts.markSubmitted(workorderId)
  const currentDraft = drafts.getByWorkorderId(workorderId)
  if (!currentDraft) return

  submissionState.value = 'uploading'
  const syncRecord = await syncStore.registerSubmission(workorder.value, currentDraft)
  submissionState.value = syncRecord.status === 'synced' ? 'synced' : syncRecord.status === 'failed' ? 'failed' : 'uploading'
  submissionError.value = syncRecord.lastError || ''
  if (syncRecord.status === 'synced' && workorder.value.source === 'remote') {
    await workorders.applyRemoteWorkorder(workorderId)
  } else if (workorder.value.source !== 'remote') {
    await workorders.setLocalStatus(workorderId, 'reviewed')
  }
  if (syncRecord.status === 'failed' || syncRecord.status === 'conflict') return
  if (ionRouter.canGoBack()) ionRouter.back()
  else ionRouter.navigate(taskDetailPath(workorderId), 'back', 'replace')
}

watch(note, (value) => {
  validationMessage.value = ''
  if (!ready.value) return
  if (noteSaveTimer) window.clearTimeout(noteSaveTimer)
  noteSaveTimer = window.setTimeout(() => {
    void drafts.updateNote(workorderId, value)
  }, 350)
})

onMounted(restoreDraft)
onBeforeUnmount(() => {
  if (noteSaveTimer) window.clearTimeout(noteSaveTimer)
  if (ready.value) void drafts.updateNote(workorderId, note.value)
})
</script>

<template>
  <IonPage>
    <IonHeader class="ion-no-border">
      <IonToolbar>
        <IonButtons slot="start">
          <IonBackButton default-href="/tabs/tasks" text="" />
        </IonButtons>
        <IonTitle>现场反馈</IonTitle>
      </IonToolbar>
    </IonHeader>

    <IonContent v-if="workorder" :fullscreen="true">
      <main class="feedback-page page-shell">
        <section class="task-summary">
          <span>{{ workorder.taskId }}</span>
          <h1>{{ workorder.title }}</h1>
          <p>{{ workorder.area }}</p>
        </section>

        <section class="panel">
          <div class="section-heading">
            <div>
              <span class="eyebrow">现场影像</span>
              <h2>补充处置凭证</h2>
            </div>
            <span class="required-tip">1 张必填</span>
          </div>
          <div class="photo-grid">
            <button type="button" class="photo-slot" :class="{ captured: fieldPhoto }" @click="capturePhoto('after')">
              <IonSpinner v-if="capturing === 'after'" name="crescent" />
              <img v-else-if="photoPreview" :src="photoPreview" alt="现场处置影像" />
              <IonIcon v-else :icon="cameraOutline" />
              <strong>现场处置影像</strong>
              <span v-if="fieldPhoto">{{ formatSize(fieldPhoto.sizeBytes) }} · {{ formatTime(fieldPhoto.capturedAt) }}</span>
              <span v-else>点击拍摄或选择</span>
            </button>
          </div>
          <p v-if="captureError" class="field-error">{{ captureError }}</p>
        </section>

        <section class="panel location-panel">
          <div class="location-icon">
            <IonSpinner v-if="locating" name="crescent" />
            <IonIcon v-else :icon="draft?.location ? checkmarkCircleOutline : locationOutline" />
          </div>
          <div>
            <strong>{{ draft?.location ? '现场位置已记录' : '记录现场作业位置' }}</strong>
            <p v-if="draft?.location">
              {{ draft.location.latitude.toFixed(6) }}, {{ draft.location.longitude.toFixed(6) }}
              · 精度 {{ draft.location.accuracy }} 米
            </p>
            <p v-else>{{ locationError || '用于核验人员确实到达目标区域' }}</p>
          </div>
          <IonButton size="small" fill="outline" :disabled="locating" @click="captureLocation">
            <IonIcon slot="start" :icon="locateOutline" />
            {{ draft?.location ? '重定位' : '定位' }}
          </IonButton>
        </section>

        <section class="panel">
          <div class="section-heading">
            <div>
              <span class="eyebrow">处置说明</span>
              <h2>记录现场情况与措施</h2>
            </div>
          </div>
          <IonTextarea
            v-model="note"
            class="feedback-input"
            :auto-grow="true"
            :counter="true"
            :maxlength="300"
            placeholder="例如：已设置警示标识，并对松动护坡进行临时加固……"
          />
        </section>

        <section class="draft-state surface">
          <IonIcon :icon="cloudDoneOutline" />
          <div>
            <strong>现场草稿自动保存</strong>
            <span v-if="draft">最近保存 {{ formatTime(draft.updatedAt) }}</span>
          </div>
          <IonIcon :icon="timeOutline" />
        </section>
      </main>
    </IonContent>

    <IonContent v-else>
      <div class="empty-state">未找到对应任务</div>
    </IonContent>

    <IonFooter v-if="workorder" class="feedback-footer ion-no-border">
      <IonToolbar>
        <p v-if="validationMessage" class="validation-message">{{ validationMessage }}</p>
        <div v-if="submissionState !== 'idle'" class="submission-state" :class="`is-${submissionState}`">
          <IonSpinner v-if="submissionState === 'saving' || submissionState === 'uploading'" name="crescent" />
          <IonIcon v-else :icon="submissionState === 'synced' ? checkmarkCircleOutline : cloudDoneOutline" />
          <span>{{ submissionState === 'saving' ? '正在保存现场记录…' : submissionState === 'uploading' ? '正在上传现场证据…' : submissionState === 'synced' ? '服务端已接收，进入人工复核' : submissionError || '提交失败，可到同步中心重试' }}</span>
        </div>
        <IonButton expand="block" size="large" :disabled="submissionState === 'saving' || submissionState === 'uploading'" :class="{ ready: canSubmit }" @click="submitFeedback">
          {{ submissionState === 'failed' ? '重新提交' : '提交复核' }}
        </IonButton>
      </IonToolbar>
    </IonFooter>
  </IonPage>
</template>

<style scoped>
.feedback-page { padding-top: 18px; padding-bottom: 28px; }
.task-summary { padding: 4px 2px 16px; }
.task-summary span, .eyebrow { color: var(--app-muted); font-size: 10px; font-weight: 700; letter-spacing: .08em; }
.task-summary h1 { margin: 7px 0 5px; color: var(--app-ink); font-size: 22px; line-height: 1.35; }
.task-summary p, .location-panel p { margin: 0; color: var(--app-muted); font-size: 10px; line-height: 1.5; }
.panel { margin-bottom: 14px; border: 1px solid var(--app-border); border-radius: 20px; padding: 18px; background: var(--app-surface); box-shadow: var(--app-shadow-soft); }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.section-heading h2 { margin: 5px 0 0; color: var(--app-ink); font-size: 17px; }
.required-tip { color: var(--ion-color-secondary); font-size: 10px; font-weight: 700; }
.photo-grid { display: grid; grid-template-columns: 1fr; }
.photo-slot { display: flex; min-height: 146px; overflow: hidden; align-items: center; justify-content: center; flex-direction: column; gap: 7px; border: 1px dashed rgba(var(--ion-color-primary-rgb), .42); border-radius: 16px; padding: 10px 8px; color: var(--app-ink); background: rgba(var(--ion-color-primary-rgb), .05); }
.photo-slot ion-icon, .photo-slot ion-spinner { color: var(--ion-color-primary); font-size: 28px; }
.photo-slot strong { font-size: 12px; }
.photo-slot span { color: var(--app-muted); font-size: 8px; }
.photo-slot img { width: 100%; height: 82px; border-radius: 10px; object-fit: cover; }
.photo-slot.captured { border-style: solid; border-color: rgba(57,201,138,.35); }
.field-error { margin: 10px 0 0; color: #ff9a94; font-size: 9px; text-align: center; }
.location-panel { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 11px; }
.location-icon { display: grid; width: 42px; height: 42px; place-items: center; border-radius: 14px; color: var(--ion-color-secondary); background: rgba(var(--ion-color-secondary-rgb), .1); }
.location-icon ion-icon, .location-icon ion-spinner { font-size: 22px; }
.location-panel strong { display: block; margin-bottom: 4px; color: var(--app-ink); font-size: 12px; }
.location-panel ion-button { min-height: 34px; margin: 0; font-size: 9px; --border-radius: 10px; }
.feedback-input { min-height: 128px; border-radius: 14px; padding: 4px 12px; --background: var(--app-background); --color: var(--app-ink); --placeholder-color: var(--app-muted); }
.draft-state { display: grid; grid-template-columns: 30px 1fr auto; align-items: center; gap: 8px; padding: 12px 14px; color: #63e3af; }
.draft-state > ion-icon:first-child { font-size: 20px; }
.draft-state > ion-icon:last-child { color: #63778d; font-size: 15px; }
.draft-state strong, .draft-state span { display: block; }
.draft-state strong { font-size: 10px; }
.draft-state span { margin-top: 3px; color: #71849a; font-size: 8px; }
.feedback-footer ion-toolbar { padding: 8px 16px calc(8px + env(safe-area-inset-bottom)); --background: rgba(8,22,37,.98); }
.feedback-footer ion-button { min-height: 50px; font-weight: 700; --border-radius: 15px; }
.feedback-footer ion-button.ready { --background: linear-gradient(100deg, #2778e7, #22b8c7); }
.validation-message { margin: 0 4px 7px; color: #ff9a94; font-size: 10px; line-height: 1.4; text-align: center; }
.submission-state { display: flex; align-items: center; gap: 7px; margin: 0 4px 7px; color: #9bb0c5; font-size: 10px; }.submission-state.is-synced { color: #63e3af; }.submission-state.is-failed { color: #ff9a94; }.submission-state ion-spinner { width: 16px; height: 16px; color: #55d8df; }
.empty-state { display: grid; min-height: 70vh; place-items: center; color: var(--app-muted); }
</style>

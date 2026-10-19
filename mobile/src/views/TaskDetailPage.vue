<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { Map as LeafletMap, Marker } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonContent,
  IonFooter,
  IonHeader,
  IonIcon,
  IonPage,
  IonProgressBar,
  IonModal,
  IonTitle,
  IonToast,
  IonToolbar,
  useIonRouter,
} from '@ionic/vue'
import {
  cameraOutline,
  checkmarkCircle,
  ellipseOutline,
  locationOutline,
  navigateOutline,
  shieldCheckmarkOutline,
  sparklesOutline,
  timeOutline,
} from 'ionicons/icons'
import { useWorkorderStore } from '@/stores/workorders'
import { riskLevelLabels, statusLabels } from '@/domain/workorder'
import { taskFeedbackPath } from '@/router/paths'
import { navigationService } from '@/services/navigationService'
import EvidencePreview from '@/components/EvidencePreview.vue'
import type { MobileEvidence } from '@/domain/workorder'

const route = useRoute()
const ionRouter = useIonRouter()
const store = useWorkorderStore()
const item = computed(() => store.getById(String(route.params.id)))
const toastMessage = ref('')
const showToast = ref(false)
const actionPending = ref(false)
const selectedEvidence = ref<MobileEvidence | null>(null)
const mapHost = ref<HTMLElement | null>(null)
const mapReady = ref(false)
const tileReady = ref(false)
const tileError = ref(false)
const liveTilesReady = ref(false)
let detailMap: LeafletMap | undefined
let detailMarker: Marker | undefined
let leaflet: typeof import('leaflet') | undefined
let detailTileLayer: import('leaflet').TileLayer | undefined
let detailTileTimer: ReturnType<typeof setTimeout> | undefined
const evidenceGroups = computed(() => {
  if (!item.value) return []
  const groups: Record<string, { label: string; items: typeof item.value.evidence }> = {}
  const labels: Record<string, string> = { image: '影像证据', change: '变化检测', geometry: '几何与点云', rule: '空间约束' }
  for (const evidence of item.value.evidence) {
    const key = evidence.type
    groups[key] ||= { label: labels[key] || '分析证据', items: [] }
    groups[key].items.push(evidence)
  }
  return Object.values(groups)
})

async function initDetailMap() {
  await nextTick()
  if (!mapHost.value || !item.value?.latitude || !item.value.longitude) return
  leaflet = await import('leaflet')
  const cachedBounds = leaflet.latLngBounds([23.565, 109.625], [23.64, 109.695])
  detailMap = leaflet.map(mapHost.value, {
    zoomControl: false,
    attributionControl: false,
    minZoom: 12,
    maxBounds: cachedBounds,
    maxBoundsViscosity: 1,
  }).setView([item.value.latitude, item.value.longitude], 16)
  leaflet.control.zoom({ position: 'bottomright' }).addTo(detailMap)
  let successfulTileCount = 0
  detailTileLayer = leaflet.tileLayer('/maps/osm/{z}/{x}/{y}.png', {
    maxNativeZoom: 17,
    maxZoom: 20,
    keepBuffer: 2,
    updateWhenIdle: true,
  })
    .on('tileload', () => { successfulTileCount += 1 })
    .on('load', () => { if (successfulTileCount > 0) { liveTilesReady.value = true; tileError.value = false } })
    .on('tileerror', () => { if (!tileReady.value) tileError.value = true })
    .addTo(detailMap)
  detailTileTimer = setTimeout(() => {
    if (!tileReady.value) tileError.value = true
  }, 5000)
  const color = item.value.riskLevel === 'high' ? '#fb7185' : '#a78bfa'
  const icon = leaflet.divIcon({ className: 'detail-map-marker', html: `<span style="--marker:${color}"><b>${item.value.confidence}</b></span>`, iconSize: [38, 38], iconAnchor: [19, 19] })
  detailMarker = leaflet.marker([item.value.latitude, item.value.longitude], { icon }).addTo(detailMap).bindTooltip(item.value.title, { direction: 'top' })
  mapReady.value = true
}

onMounted(async () => {
  if (item.value?.source !== 'remote') return
  try {
    await store.applyRemoteWorkorder(item.value.id)
  } catch {}
  await initDetailMap()
})

onBeforeUnmount(() => { if (detailTileTimer) clearTimeout(detailTileTimer); detailTileLayer?.remove(); detailMarker?.remove(); detailMap?.remove(); detailMap = undefined })

const workflowStages = [
  { label: '智能发现', caption: '多源数据筛查' },
  { label: 'AI 研判', caption: '风险证据融合' },
  { label: '任务派发', caption: '责任到人' },
  { label: '现场处置', caption: '核查与回传' },
  { label: '人工复核', caption: '闭环归档' },
]

const currentStage = computed(() => {
  if (!item.value) return 0
  return {
    todo: 2,
    assigned: 3,
    in_progress: 3,
    reviewed: 4,
    closed: 5,
  }[item.value.status]
})

const deadlineLabel = computed(() => {
  if (!item.value) return ''
  return new Date(item.value.deadline).toLocaleString('zh-CN', {
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
})

async function primaryAction() {
  if (!item.value) return
  actionPending.value = true
  try {
    if (item.value.status === 'todo') {
      await store.setStatus(item.value.id, 'assigned')
      toastMessage.value = '任务已接收并同步'
      showToast.value = true
    } else if (item.value.status === 'assigned') {
      await store.setStatus(item.value.id, 'in_progress')
      toastMessage.value = '已进入现场处置阶段'
      showToast.value = true
    } else if (item.value.status === 'in_progress') {
      ionRouter.push(taskFeedbackPath(item.value.id))
    } else {
      ionRouter.navigate('/tabs/tasks', 'root', 'replace')
    }
  } catch (error) {
    toastMessage.value = error instanceof Error ? error.message : '任务状态同步失败'
    showToast.value = true
  } finally {
    actionPending.value = false
  }
}

const actionLabel = computed(() => {
  if (!item.value) return ''
  if (item.value.status === 'todo') return '接受任务'
  if (item.value.status === 'assigned') return '开始现场处置'
  if (item.value.status === 'in_progress') return '填写现场反馈'
  if (item.value.status === 'reviewed') return '返回任务中心'
  return '返回任务中心'
})

function openNavigation() {
  if (!item.value) return
  try {
    navigationService.open(item.value.latitude, item.value.longitude, item.value.title)
  } catch (error) {
    toastMessage.value = error instanceof Error ? error.message : '无法打开导航'
    showToast.value = true
  }
}
</script>

<template>
  <IonPage>
    <IonHeader class="ion-no-border">
      <IonToolbar>
        <IonButtons slot="start"><IonBackButton default-href="/tabs/tasks" text="" /></IonButtons>
        <IonTitle>工单详情</IonTitle>
      </IonToolbar>
    </IonHeader>
    <IonContent v-if="item">
      <div class="page-shell detail-shell">
        <section v-if="item.status === 'reviewed'" class="submission-banner">
          <IonIcon :icon="checkmarkCircle" />
          <div>
            <strong>现场反馈已提交</strong>
            <span>影像和处置记录已进入人工复核</span>
          </div>
        </section>
        <section class="hero surface">
          <div class="hero-top">
            <span class="risk-pill" :class="item.riskLevel === 'high' ? 'risk-high' : 'risk-review'">{{ riskLevelLabels[item.riskLevel] }}</span>
            <span class="status-pill">{{ statusLabels[item.status] }}</span>
          </div>
          <h1>{{ item.title }}</h1>
          <p>{{ item.summary }}</p>
          <div class="deadline">
            <IonIcon :icon="timeOutline" />
            <span>处置时限</span>
            <strong>{{ deadlineLabel }}</strong>
          </div>
          <div class="scores">
            <div><span>AI 置信度</span><strong>{{ item.confidence }}%</strong></div>
            <div><span>不确定性</span><strong>{{ item.uncertainty }}%</strong></div>
            <div><span>闭环进度</span><strong>{{ item.progress }}%</strong></div>
          </div>
          <IonProgressBar :value="item.progress / 100" />
        </section>

        <section class="workflow surface">
          <div class="section-title workflow-title">
            <div><span class="eyebrow">CLOSED LOOP</span><h2>五阶段处置闭环</h2></div>
            <small>当前：{{ workflowStages[Math.min(currentStage, 4)].label }}</small>
          </div>
          <div class="stage-list">
            <div
              v-for="(stage, index) in workflowStages"
              :key="stage.label"
              class="stage"
              :class="{ done: index < currentStage, current: index === currentStage && item.status !== 'closed' }"
            >
              <div class="stage-node">
                <IonIcon :icon="index < currentStage ? checkmarkCircle : ellipseOutline" />
              </div>
              <div><strong>{{ stage.label }}</strong><span>{{ stage.caption }}</span></div>
            </div>
          </div>
        </section>

        <section class="location surface">
          <div class="map-preview" :class="{ 'map-ready': mapReady }">
            <img class="cached-map-image" src="/maps/guigang-task-area.jpg" alt="任务区域真实地图" @load="tileReady = true; tileError = false" @error="tileError = true">
            <div ref="mapHost" class="map-leaflet" />
            <div v-if="!tileReady" class="map-loading">{{ tileError ? '地图底图服务不可达 · 请检查网络' : '正在加载真实地图…' }}</div>
            <span><IonIcon :icon="locationOutline" />目标位置</span>
          </div>
          <div class="location-footer">
            <div><strong>{{ item.area }}</strong><span>距当前位置 {{ item.distanceMeters }} 米</span></div>
            <IonButton size="small" fill="outline" @click="openNavigation"><IonIcon slot="start" :icon="navigateOutline" />导航</IonButton>
          </div>
        </section>

        <section>
          <div class="section-title"><div><span class="eyebrow">AI EVIDENCE</span><h2>风险判断依据</h2></div><small>{{ item.evidence.length }} 项证据</small></div>
          <div v-for="group in evidenceGroups" :key="group.label" class="evidence-group">
            <h3>{{ group.label }} <small>{{ group.items.length }}</small></h3>
            <div class="evidence-grid">
            <article v-for="evidence in group.items" :key="evidence.id" class="surface" @click="selectedEvidence = evidence">
              <EvidencePreview
                :url="evidence.previewUrl"
                :alt="evidence.title"
                :kind="evidence.previewKind"
                :media-type="evidence.mediaType"
              />
              <div><IonIcon :icon="shieldCheckmarkOutline" /><span>{{ evidence.score }}%</span></div>
              <strong>{{ evidence.title }}</strong>
              <p>{{ evidence.summary }}</p>
              <small>{{ evidence.metric }}</small>
            </article>
            </div>
          </div>
        </section>

        <section class="timeline surface">
          <div class="section-title"><div><span class="eyebrow">TRACEABILITY</span><h2>任务处理时间线</h2></div></div>
          <div v-for="event in item.timeline" :key="event.id" class="timeline-item" :class="`is-${event.state}`">
            <i />
            <div><strong>{{ event.label }}</strong><span>{{ event.detail }}</span><small v-if="event.at">{{ new Date(event.at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }}</small></div>
          </div>
        </section>

        <section class="recommendation surface">
          <span class="eyebrow"><IonIcon :icon="sparklesOutline" /> AI 建议处置</span>
          <p>{{ item.recommendedAction }}</p>
        </section>

        <section class="people surface">
          <div><span>现场责任人</span><strong>{{ item.assignee }}</strong></div>
          <div><span>复核人</span><strong>{{ item.reviewer }}</strong></div>
        </section>
      </div>
    </IonContent>
    <IonFooter v-if="item" class="ion-no-border detail-footer">
      <IonToolbar>
        <div class="footer-actions">
          <IonButton fill="outline" @click="ionRouter.push({ path: '/tabs/map', query: { task: item.id } })"><IonIcon slot="start" :icon="locationOutline" />查看位置</IonButton>
          <IonButton :disabled="actionPending" @click="primaryAction">
            <IonIcon v-if="item.status === 'in_progress'" slot="start" :icon="cameraOutline" />{{ actionLabel }}
          </IonButton>
        </div>
      </IonToolbar>
    </IonFooter>
    <IonModal :is-open="Boolean(selectedEvidence)" @did-dismiss="selectedEvidence = null">
      <IonHeader><IonToolbar><IonTitle>{{ selectedEvidence?.title || '证据详情' }}</IonTitle><IonButtons slot="end"><IonButton @click="selectedEvidence = null">关闭</IonButton></IonButtons></IonToolbar></IonHeader>
      <IonContent v-if="selectedEvidence" class="evidence-modal-content">
        <EvidencePreview :url="selectedEvidence.previewUrl" :alt="selectedEvidence.title" :kind="selectedEvidence.previewKind" :media-type="selectedEvidence.mediaType" />
        <div class="modal-copy"><h2>{{ selectedEvidence.title }}</h2><p>{{ selectedEvidence.summary }}</p><span>{{ selectedEvidence.metric }} · 置信度 {{ selectedEvidence.score }}%</span></div>
      </IonContent>
    </IonModal>
    <IonToast
      :is-open="showToast"
      :message="toastMessage"
      :duration="1400"
      position="top"
      @did-dismiss="showToast = false"
    />
  </IonPage>
</template>

<style scoped>
.detail-shell { display: grid; gap: 15px; padding-bottom: 28px; }
.submission-banner { display: flex; align-items: center; gap: 10px; border: 1px solid rgba(57,201,138,.2); border-radius: 14px; padding: 12px 14px; color: #63e3af; background: rgba(57,201,138,.07); }
.submission-banner ion-icon { flex: 0 0 auto; font-size: 22px; }
.submission-banner strong, .submission-banner span { display: block; }
.submission-banner strong { font-size: 12px; }
.submission-banner span { margin-top: 3px; color: #87a99d; font-size: 9px; }
.hero { padding: 17px; }
.hero-top { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
.risk-pill, .status-pill { border-radius: 999px; padding: 5px 9px; font-size: 9px; font-weight: 700; }
.risk-pill { background: rgba(255, 93, 93, 0.11); }
.status-pill { border: 1px solid rgba(148, 180, 208, 0.13); color: #9bb0c5; }
h1 { overflow-wrap: anywhere; margin: 15px 0 0; font-size: 20px; line-height: 1.4; }
.hero > p { margin: 8px 0 0; color: #8296ac; font-size: 11px; line-height: 1.7; }
.deadline { display: flex; align-items: center; gap: 5px; margin-top: 12px; border-radius: 10px; padding: 8px 10px; color: #71849a; background: rgba(47,128,237,.07); font-size: 9px; }
.deadline ion-icon { color: #55d8df; }
.deadline strong { margin-left: auto; color: #c9d6e2; font-size: 10px; text-align: right; }
.scores { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 16px; border-top: 1px solid rgba(148, 180, 208, 0.09); padding-top: 13px; }
.scores div { text-align: center; }
.scores div + div { border-left: 1px solid rgba(148, 180, 208, 0.09); }
.scores span, .people span { display: block; color: #6f8399; font-size: 9px; }
.scores strong { display: block; margin-top: 4px; color: #55d8df; font-size: 17px; }
.hero ion-progress-bar { height: 3px; margin-top: 12px; border-radius: 999px; --background: rgba(148,180,208,.1); --progress-background: linear-gradient(90deg, #2f80ed, #2dd4bf); }
.workflow { padding: 15px; }
.workflow-title { margin: 0 0 14px; }
.stage-list { display: grid; grid-template-columns: repeat(5, 1fr); }
.stage { position: relative; min-width: 0; color: #556b81; text-align: center; }
.stage::before { position: absolute; top: 10px; right: 50%; left: -50%; height: 1px; background: rgba(148,180,208,.12); content: ''; }
.stage:first-child::before { display: none; }
.stage.done::before, .stage.current::before { background: rgba(45,212,191,.46); }
.stage-node { position: relative; z-index: 1; display: grid; width: 21px; height: 21px; margin: 0 auto; place-items: center; border-radius: 50%; color: #556b81; background: #0a1929; font-size: 14px; }
.stage.done .stage-node { color: #63e3af; }
.stage.current .stage-node { color: #7fe8ee; box-shadow: 0 0 0 5px rgba(85,216,223,.08); }
.stage strong, .stage span { display: block; }
.stage strong { margin-top: 7px; color: #71849a; font-size: 9px; white-space: nowrap; }
.stage.done strong, .stage.current strong { color: #cfe2ee; }
.stage span { display: none; margin-top: 3px; font-size: 7px; }
.location { overflow: hidden; }
.map-preview { position: relative; height: 142px; overflow: hidden; background: #07111f; }
.cached-map-image { position: absolute; z-index: 0; inset: 0; display: block; width: 100%; height: 100%; opacity: .72; object-fit: cover; filter: saturate(.82) brightness(.72) contrast(1.12); }
.map-leaflet { position: absolute; z-index: 1; inset: 0; background: transparent; }
.map-preview .leaflet-container { width: 100%; height: 100%; background: transparent; font-family: inherit; }
.map-preview .leaflet-tile-pane { filter: saturate(.9) brightness(.86) contrast(1.08); }
.map-preview .leaflet-tile { opacity: 1 !important; mix-blend-mode: normal !important; }
.map-preview .leaflet-tile:not(.leaflet-tile-loaded) { visibility: hidden !important; }
.map-preview .leaflet-control-attribution { background: rgba(7,17,31,.78) !important; color: #94a3b8; font-size: 7px !important; }
.map-preview .leaflet-control-attribution a { color: #67e8f9; }
.map-preview .leaflet-control-zoom a { border-color: rgba(255,255,255,.1) !important; background: rgba(7,17,31,.88) !important; color: #cbd5e1 !important; }
.map-loading { position: absolute; z-index: 500; top: 10px; left: 10px; border-radius: 7px; background: rgba(7,17,31,.88); padding: 6px 8px; color: #f4c86a; font-size: 8px; }
.map-preview > span { position: absolute; z-index: 2; top: 10px; left: 10px; display: flex; align-items: center; gap: 4px; border-radius: 7px; background: rgba(0,0,0,.48); padding: 6px 8px; font-size: 9px; }
.location-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 13px; }
.location-footer > div { min-width: 0; }
.location-footer strong, .location-footer span { display: block; }
.location-footer strong { font-size: 12px; }
.location-footer span { margin-top: 3px; color: #71849a; font-size: 9px; }
.section-title { display: flex; align-items: end; justify-content: space-between; margin: 3px 2px 10px; }
.section-title h2 { margin: 3px 0 0; font-size: 15px; }
.section-title small { color: #71849a; font-size: 9px; }
.evidence-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 9px; }
.evidence-group h3 { margin: 12px 2px 7px; color: #9bb0c5; font-size: 10px; }
.evidence-group h3 small { margin-left: 4px; color: #55d8df; }
.evidence-grid article { cursor: pointer; }
.evidence-grid article { padding: 12px; }
.evidence-grid article > .evidence-preview { width: calc(100% + 24px); margin: -12px -12px 10px; border-radius: 14px 14px 8px 8px; }
.evidence-grid article > div { display: flex; align-items: center; justify-content: space-between; color: #55d8df; font-size: 10px; }
.evidence-grid strong { display: block; margin-top: 10px; font-size: 12px; }
.evidence-grid p { min-height: 34px; margin: 5px 0 0; color: #71849a; font-size: 9px; line-height: 1.5; }
.evidence-grid small { display: block; margin-top: 7px; color: #9bb0c5; font-size: 9px; }
.recommendation { padding: 14px; }
.recommendation .eyebrow { display: flex; align-items: center; gap: 4px; }
.recommendation p { margin: 7px 0 0; color: #c9d6e2; font-size: 11px; line-height: 1.7; }
.people { display: grid; grid-template-columns: repeat(2, 1fr); padding: 13px; }
.people div { text-align: center; }
.people div + div { border-left: 1px solid rgba(148, 180, 208, 0.09); }
.people strong { display: block; margin-top: 4px; font-size: 12px; }
.detail-footer ion-toolbar { --background: rgba(8, 22, 37, .98); --border-color: rgba(148, 180, 208, .12); }
.footer-actions { display: grid; grid-template-columns: .8fr 1.2fr; gap: 8px; padding: 8px 12px max(8px, env(safe-area-inset-bottom)); }
.footer-actions ion-button { margin: 0; min-width: 0; min-height: 42px; font-size: 11px; }
.detail-map-marker { border: 0; background: transparent; }
.detail-map-marker span { display: grid; width: 38px; height: 38px; place-items: center; border: 2px solid rgba(255,255,255,.92); border-radius: 50% 50% 50% 4px; transform: rotate(-45deg); background: var(--marker); color: #fff; box-shadow: 0 0 18px var(--marker); }
.detail-map-marker b { transform: rotate(45deg); font-size: 9px; }
.timeline { padding: 14px; }
.timeline-item { position: relative; display: grid; grid-template-columns: 18px 1fr; gap: 8px; min-height: 49px; }
.timeline-item i { position: relative; z-index: 1; width: 10px; height: 10px; margin: 3px 0 0 2px; border: 2px solid #536a80; border-radius: 50%; background: #07111f; }
.timeline-item:not(:last-child) i::after { position: absolute; top: 8px; left: 2px; width: 2px; height: 50px; background: rgba(148,180,208,.16); content: ''; }
.timeline-item.is-done i { border-color: #63e3af; background: #63e3af; }.timeline-item.is-current i { border-color: #55d8df; box-shadow: 0 0 0 4px rgba(85,216,223,.13); }
.timeline-item strong, .timeline-item span, .timeline-item small { display: block; }.timeline-item strong { font-size: 11px; }.timeline-item span { margin-top: 3px; color: #71849a; font-size: 9px; }.timeline-item small { margin-top: 4px; color: #52677d; font-size: 8px; }
.evidence-modal-content { --background: #07111f; }.evidence-modal-content .evidence-preview { height: 260px; margin: 16px; border-radius: 16px; }.modal-copy { padding: 0 18px 28px; }.modal-copy h2 { font-size: 18px; }.modal-copy p { color: #9bb0c5; font-size: 12px; line-height: 1.7; }.modal-copy span { color: #55d8df; font-size: 10px; }

@media (min-width: 600px) {
  .stage span { display: block; }
  .map-preview { height: 178px; }
}

@media (max-width: 480px) {
  .detail-shell { gap: 12px; padding: 12px 12px 24px; }
  .hero { padding: 15px; }
  h1 { margin-top: 12px; font-size: 18px; line-height: 1.35; }
  .hero > p { font-size: 10px; }
  .deadline { flex-wrap: wrap; row-gap: 4px; }
  .deadline strong { flex: 1 0 100%; margin-left: 19px; text-align: left; }
  .scores { margin-top: 13px; padding-top: 11px; }
  .scores strong { font-size: 15px; }
  .workflow { padding: 14px 15px; }
  .workflow-title { align-items: flex-start; gap: 10px; }
  .workflow-title small { flex: 0 0 auto; padding-top: 3px; }
  .stage-list { display: grid; grid-template-columns: 1fr; gap: 0; }
  .stage { display: grid; grid-template-columns: 27px minmax(0, 1fr); align-items: center; min-height: 43px; text-align: left; }
  .stage::before { top: -50%; right: auto; bottom: 50%; left: 10px; width: 1px; height: auto; }
  .stage-node { width: 21px; height: 21px; margin: 0; }
  .stage strong { margin-top: 0; font-size: 10px; }
  .stage span { display: block; margin-top: 2px; color: #60758b; font-size: 8px; }
  .evidence-grid { grid-template-columns: 1fr; }
  .evidence-grid article { display: grid; grid-template-columns: 88px minmax(0, 1fr); column-gap: 12px; }
  .evidence-grid article > .evidence-preview { grid-row: 1 / 5; width: 88px; height: 88px; margin: 0; border-radius: 10px; }
  .evidence-grid article > div,
  .evidence-grid article > strong,
  .evidence-grid article > p,
  .evidence-grid article > small { grid-column: 2; }
  .evidence-grid strong { margin-top: 7px; }
  .evidence-grid p { min-height: 0; }
  .people { padding: 12px; }
}

@media (max-width: 350px) {
  .detail-shell { padding-right: 10px; padding-left: 10px; }
  .section-title { align-items: flex-start; gap: 8px; }
  .location-footer { align-items: flex-start; }
  .location-footer ion-button { flex: 0 0 auto; }
  .people { grid-template-columns: 1fr; gap: 11px; }
  .people div + div { border-top: 1px solid rgba(148, 180, 208, 0.09); border-left: 0; padding-top: 11px; }
  .footer-actions { grid-template-columns: 1fr; }
  .footer-actions ion-button { min-height: 38px; }
}
</style>

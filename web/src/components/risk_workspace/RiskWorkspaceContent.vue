<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import * as ZoneService from '@/data/ZoneService'
import * as TaskService from '@/data/TaskService'
import * as WorkorderService from '@/data/WorkorderService'
import type { RiskEventData } from '@/data/RiskEventData'
import type { WorkorderData } from '@/data/WorkorderData'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'
import type { AgentVisualizationData } from '@/lib/api-contracts'
import { localAgentRuntime } from '@/lib/local-agent-runtime'
import { remoteAgentProvider } from '@/lib/remote-agent-provider'
import { getRemoteAgentBinding, getRemoteAgentSnapshot } from '@/lib/remote-agent-storage'
import { remoteAgentApi } from '@/api/remote-agent-api'
import type { RemoteWorkorder } from '@/lib/remote-workorder-types'
import { buildRisksFromAgentSnapshot, getAgentRiskContext } from '@/lib/agent-risk-presentation'
import { useSpatialSelection, type SpatialSelectionSource } from '@/lib/spatial-selection'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import SafeIcon from '@/components/common/SafeIcon.vue'
import MultiModalEvidenceCanvas from './MultiModalEvidenceCanvas.vue'
import RiskDetailCard from './RiskDetailCard.vue'
import RiskListTable from './RiskListTable.vue'

const isClientReady = ref(false)
const isSynchronizing = ref(false)
const allZones = ref(ZoneService.getAll())
const allRisks = ref<RiskEventData[]>([])
const taskId = ref<string | null>(null)
const zoneId = ref<string | null>(null)
const riskLevelFilter = ref<RiskEventData['level'] | 'all'>('all')
const sortBy = ref<'level' | 'score'>('level')
const agentSnapshot = ref<AgentPresentationSnapshot | null>(null)
const remoteWorkorders = ref<RemoteWorkorder[]>([])
const spatialSelection = useSpatialSelection()
const { selectedRiskId, selectedRegionId, hoveredRiskId, activeView } = spatialSelection

const currentTask = computed(() => taskId.value ? TaskService.getById(taskId.value) : null)
const selectedRiskContext = computed(() => agentSnapshot.value && selectedRiskId.value
  ? getAgentRiskContext(agentSnapshot.value, selectedRiskId.value)
  : undefined)
const filteredRisks = computed(() => {
  let result = allRisks.value
  if (riskLevelFilter.value !== 'all') result = result.filter((risk) => risk.level === riskLevelFilter.value)
  const order: Record<RiskEventData['level'], number> = { high: 0, medium: 1, low: 2, review_required: 3 }
  return [...result].sort((left, right) => sortBy.value === 'score' ? right.score - left.score : order[left.level] - order[right.level])
})
const selectedRisk = computed(() => allRisks.value.find((risk) => risk.id === selectedRiskId.value) || filteredRisks.value[0] || null)
const riskStats = computed(() => ({
  high: allRisks.value.filter((risk) => risk.level === 'high').length,
  reviewRequired: allRisks.value.filter((risk) => risk.level === 'review_required').length,
  artifacts: agentSnapshot.value?.evidence.artifacts.length || 0,
}))
const pointCloudArtifact = computed(() => agentSnapshot.value?.evidence.artifacts.find((artifact) => artifact.role === 'point_cloud_path'))
const semanticLabelsArtifact = computed(() => agentSnapshot.value?.evidence.artifacts.find((artifact) => artifact.role === 'point_labels' && artifact.downloadUrl))
const semanticClasses = computed(() => agentSnapshot.value?.evidence.semanticResult?.classes || [])
const selectedPointMaskArtifact = computed(() => selectedRiskContext.value?.artifacts.find((artifact) => ['target_mask', 'relation_mask'].includes(artifact.role) && artifact.downloadUrl)
  || agentSnapshot.value?.evidence.artifacts.find((artifact) => artifact.role === 'target_mask' && artifact.downloadUrl))
const selectedPointProbabilityArtifact = computed(() => selectedRiskContext.value?.artifacts.find((artifact) => artifact.role === 'target_probabilities' && artifact.downloadUrl)
  || agentSnapshot.value?.evidence.artifacts.find((artifact) => artifact.role === 'target_probabilities' && artifact.downloadUrl))
const agentVisualization = computed<AgentVisualizationData | null>(() => {
  const snapshot = agentSnapshot.value
  if (!snapshot) return null
  const findArtifact = (role: string) => snapshot.evidence.artifacts.find((artifact) => artifact.role === role)
  const beforeImage = findArtifact('before_image_path')
  const afterImage = findArtifact('after_image_path') || findArtifact('image_path')
  const changeMask = findArtifact('change_mask')
  const changeReport = findArtifact('change_regions')?.metadata?.report
  const imageSize = changeReport && typeof changeReport === 'object' && Array.isArray((changeReport as Record<string, unknown>).image_size_hw)
    ? (changeReport as Record<string, unknown>).image_size_hw as unknown[]
    : []
  const height = Number(imageSize[0]) || 720
  const width = Number(imageSize[1]) || 1280
  return {
    schemaVersion: 'remote-agent-visualization.v1',
    available: Boolean(afterImage?.previewUrl || changeMask?.previewUrl || snapshot.evidence.regions.length),
    sceneId: snapshot.task.sceneId,
    ortho: afterImage?.previewUrl ? {
      sourceFile: { fileId: afterImage.artifactId, fileName: afterImage.title, contentType: afterImage.mediaType, downloadUrl: afterImage.previewUrl },
      originalWidth: width,
      originalHeight: height,
      displayWidth: width,
      displayHeight: height,
      coordinateMode: 'after_image_pixels',
    } : undefined,
    riskOverlays: snapshot.business.risks.map((risk) => {
      const region = snapshot.evidence.regions.find((item) => item.regionId === risk.regionId)
      return {
        overlayId: risk.riskId,
        riskCardId: risk.riskId,
        regionId: risk.regionId,
        label: region?.label,
        riskType: risk.riskType,
        riskLevel: risk.riskLevel,
        riskScore: risk.score,
        reviewRequired: risk.reviewRequired,
        bboxPixel: region?.bboxPixel,
        polygonPixel: region?.polygonPixel,
        summary: region?.summary,
      }
    }),
    changeComparison: {
      status: changeMask ? 'ready' : 'limited',
      changeSummary: snapshot.evidence.summary,
      reviewRequired: snapshot.business.risks.some((risk) => risk.reviewRequired),
      preImage: beforeImage?.previewUrl ? { fileId: beforeImage.artifactId, fileName: beforeImage.title, contentType: beforeImage.mediaType, downloadUrl: beforeImage.previewUrl } : undefined,
      postImage: afterImage?.previewUrl ? { fileId: afterImage.artifactId, fileName: afterImage.title, contentType: afterImage.mediaType, downloadUrl: afterImage.previewUrl } : undefined,
      changeMask: changeMask?.previewUrl ? { fileId: changeMask.artifactId, fileName: changeMask.title, contentType: changeMask.mediaType, downloadUrl: changeMask.previewUrl } : undefined,
      canCompare: Boolean(beforeImage?.previewUrl && afterImage?.previewUrl),
      maskAvailable: Boolean(changeMask?.previewUrl),
    },
  }
})

function parseRouteParams() {
  const params = new URLSearchParams(window.location.search)
  taskId.value = params.get('taskId')
  zoneId.value = params.get('zoneId')
  spatialSelection.restoreFromUrl()
}

function selectFirstRiskIfNeeded() {
  const routeRegionRisk = selectedRegionId.value ? filteredRisks.value.find((risk) => risk.candidateRegionId === selectedRegionId.value) : undefined
  if (!selectedRiskId.value && routeRegionRisk) {
    spatialSelection.selectRisk(routeRegionRisk, 'route')
    return
  }
  if (!filteredRisks.value.some((risk) => risk.id === selectedRiskId.value)) spatialSelection.selectRisk(filteredRisks.value[0] || null, 'route')
}

function handleRiskSelection(riskId: string, source: SpatialSelectionSource) {
  const risk = allRisks.value.find((item) => item.id === riskId)
  if (risk) spatialSelection.selectRisk(risk, source)
}

function applyAgentSnapshot(snapshot: AgentPresentationSnapshot) {
  agentSnapshot.value = snapshot
  const workorders = WorkorderService.getAll()
  allRisks.value = buildRisksFromAgentSnapshot(snapshot, zoneId.value || currentTask.value?.zoneId || 'zone-01').map((risk) => {
    const agentRisk = snapshot.business.risks.find((item) => item.riskId === risk.id)
    const remote = remoteWorkorders.value.find((item) => item.candidate_id === agentRisk?.candidateId && item.region_id === (agentRisk?.regionId || ''))
    if (remote) return { ...risk, workorderId: remote.workorder_id, status: remote.status === 'closed' ? 'closed' : 'linked' }
    const existing = workorders.find((item) => item.riskId === risk.id)
    return existing ? { ...risk, workorderId: existing.id, status: existing.status === 'closed' ? 'closed' : 'linked' } : risk
  })
  selectFirstRiskIfNeeded()
}

function restoreCachedPreviewUrls(snapshot: AgentPresentationSnapshot): AgentPresentationSnapshot {
  const previewRoles = new Set(['before_image_path', 'after_image_path', 'image_path', 'change_mask', 'diagnostic_overlay'])
  return {
    ...snapshot,
    evidence: {
      ...snapshot.evidence,
      artifacts: snapshot.evidence.artifacts.map((artifact) => {
        if (artifact.previewUrl || (!artifact.mediaType.startsWith('image/') && !previewRoles.has(artifact.role))) return artifact
        return { ...artifact, previewUrl: remoteAgentApi.getPreviewUrl(artifact.artifactId) }
      }),
    },
  }
}

async function synchronizeWorkorders(jobId: string) {
  try {
    remoteWorkorders.value = await remoteAgentApi.listWorkorders({ job_id: jobId })
    if (agentSnapshot.value) applyAgentSnapshot(agentSnapshot.value)
  } catch {}
}

async function initializeAgentResult() {
  if (!taskId.value) return
  const binding = getRemoteAgentBinding(taskId.value)
  if (!binding) {
    const snapshot = localAgentRuntime.restore(taskId.value)
    if (snapshot) applyAgentSnapshot(snapshot)
    isClientReady.value = true
    return
  }

  const cached = getRemoteAgentSnapshot(taskId.value)
  if (cached) {
    applyAgentSnapshot(restoreCachedPreviewUrls(cached))
    isClientReady.value = true
  }
  isSynchronizing.value = true
  try {
    const snapshot = await remoteAgentProvider.restore(taskId.value)
    if (snapshot) applyAgentSnapshot(snapshot)
  } catch (error) {
    if (!cached) toast.error(error instanceof Error ? error.message : '真实 Agent 结果同步失败')
    else toast.warning('已展示最近一次结果，最新数据暂未同步')
  } finally {
    isSynchronizing.value = false
    isClientReady.value = true
  }
  void synchronizeWorkorders(binding.jobId)
}

async function handleCreateWorkorder() {
  if (!selectedRisk.value || !agentSnapshot.value) return
  const binding = taskId.value ? getRemoteAgentBinding(taskId.value) : undefined
  const agentRisk = agentSnapshot.value.business.risks.find((item) => item.riskId === selectedRisk.value?.id)
  if (binding && agentRisk?.candidateId) {
    try {
      const workorder = await remoteAgentApi.createWorkorder({
        job_id: binding.jobId,
        candidate_id: agentRisk.candidateId,
        region_id: agentRisk.regionId,
        task_id: taskId.value || undefined,
        priority: selectedRisk.value.level === 'high' ? 'urgent' : 'normal',
        due_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
        location: selectedRisk.value.location ? {
          longitude: selectedRisk.value.location.longitude,
          latitude: selectedRisk.value.location.latitude,
          projected_x: selectedRisk.value.location.projectedX,
          projected_y: selectedRisk.value.location.projectedY,
          epsg: selectedRisk.value.location.epsg,
          crs_name: selectedRisk.value.location.crsName,
          geographic_bbox: selectedRisk.value.location.geographicBBox,
        } : undefined,
      })
      allRisks.value = allRisks.value.map((risk) => risk.id === selectedRisk.value?.id ? { ...risk, workorderId: workorder.workorder_id, status: 'linked' } : risk)
      toast.success('处置工单已生成，风险证据已同步')
      window.location.href = `./workorder-detail.html?orderId=${encodeURIComponent(workorder.workorder_id)}`
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '处置工单生成失败')
    }
    return
  }
  const draft = agentSnapshot.value.business.workOrders.find((item) => item.riskId === selectedRisk.value?.id)
  const existing = WorkorderService.getAll().find((item) => item.riskId === selectedRisk.value?.id)
  if (existing) {
    window.location.href = `./workorder-detail.html?orderId=${encodeURIComponent(existing.id)}`
    return
  }
  const now = new Date().toISOString()
  const recommendation = draft?.recommendedAction || agentSnapshot.value.business.recommendations.join('；')
  const workorder: WorkorderData = {
    id: draft?.workOrderId || `wo-agent-${Date.now()}`,
    title: draft?.title || `${selectedRisk.value.title}现场核查`,
    riskId: selectedRisk.value.id,
    taskId: taskId.value || undefined,
    ruleId: selectedRisk.value.ruleId,
    templateId: selectedRisk.value.templateId,
    status: 'todo',
    priority: selectedRisk.value.level === 'high' ? 'urgent' : 'normal',
    dueAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    createdAt: now,
    updatedAt: now,
    summary: selectedRisk.value.description,
    aiRecommendation: recommendation,
    location: selectedRisk.value.location,
  }
  WorkorderService.savePersisted([workorder, ...WorkorderService.getAll()])
  allRisks.value = allRisks.value.map((risk) => risk.id === selectedRisk.value?.id ? { ...risk, workorderId: workorder.id, status: 'linked' } : risk)
  toast.success('处置工单已生成')
  window.location.href = `./workorder-detail.html?orderId=${encodeURIComponent(workorder.id)}`
}

function handleMarkReview() {
  if (!selectedRisk.value) return
  allRisks.value = allRisks.value.map((risk) => risk.id === selectedRisk.value?.id ? { ...risk, level: 'review_required', status: 'review_required', reviewRequired: true } : risk)
  toast.success('已进入人工复核队列')
}

function handleReturnToExecution() { if (taskId.value) window.location.href = `./task-execution-monitor.html?taskId=${taskId.value}` }
function handleGoHome() { window.location.href = './dashboard.html' }
function handleOpenAuditReport() {
  const binding = taskId.value ? getRemoteAgentBinding(taskId.value) : undefined
  if (binding) window.location.href = `./audit-report.html?jobId=${encodeURIComponent(binding.jobId)}`
}

watch(filteredRisks, selectFirstRiskIfNeeded)
onMounted(async () => {
  parseRouteParams()
  await initializeAgentResult()
})
</script>

<template>
  <div v-if="isClientReady && agentSnapshot" class="flex h-full flex-col overflow-hidden bg-background">
    <div class="flex-shrink-0 border-b border-border/50 bg-[#07111f]/95 px-5 py-3 backdrop-blur-xl"><div class="flex flex-wrap items-center justify-between gap-4"><div class="flex min-w-0 items-center gap-2"><Button variant="ghost" size="icon" class="h-8 w-8" title="返回首页" @click="handleGoHome"><SafeIcon name="Home" :size="18" /></Button><span class="text-sm text-muted-foreground">/</span><div class="min-w-0"><div class="flex items-center gap-2"><h1 class="whitespace-nowrap text-lg font-semibold">Agent 风险研判中心</h1><span class="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2 py-0.5 text-[10px] font-semibold text-cyan-300">EVIDENCE CHAIN</span><span v-if="isSynchronizing" class="inline-flex items-center gap-1.5 text-[10px] text-cyan-200/80"><span class="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-300" />正在同步最新结果</span></div><p class="mt-0.5 truncate text-[11px] text-muted-foreground">{{ currentTask?.name || agentSnapshot.task.objective }} · {{ agentSnapshot.evidence.summary }}</p></div></div><div class="flex items-center gap-3"><div class="hidden items-center gap-3 lg:flex"><div class="text-right"><div class="text-[10px] text-muted-foreground">高风险</div><div class="text-sm font-semibold text-[#ff837c]">{{ riskStats.high }}</div></div><div class="h-7 w-px bg-border/60" /><div class="text-right"><div class="text-[10px] text-muted-foreground">待复核</div><div class="text-sm font-semibold text-[#b8adff]">{{ riskStats.reviewRequired }}</div></div><div class="h-7 w-px bg-border/60" /><div class="text-right"><div class="text-[10px] text-muted-foreground">证据产物</div><div class="text-sm font-semibold text-[#63e3af]">{{ riskStats.artifacts }}</div></div></div><Button v-if="taskId && getRemoteAgentBinding(taskId)" variant="outline" size="sm" class="gap-2" @click="handleOpenAuditReport"><SafeIcon name="FileCheck2" :size="14" />审计报告</Button><Button variant="outline" size="sm" class="gap-2" @click="handleReturnToExecution"><SafeIcon name="ArrowLeft" :size="14" />返回智能执行</Button></div></div></div>
    <div class="flex-1 min-h-0 overflow-y-auto p-3 xl:overflow-hidden"><div class="grid min-h-full grid-cols-1 gap-3 min-[1400px]:h-full min-[1400px]:grid-cols-[250px_minmax(420px,1fr)_360px] 2xl:grid-cols-[286px_minmax(520px,1fr)_390px]">
      <section class="flex min-h-[420px] flex-col overflow-hidden rounded-[18px] border border-border/60 bg-card/35 xl:min-h-0"><div class="grid grid-cols-2 gap-2 border-b border-border/50 p-2"><Select v-model="riskLevelFilter"><SelectTrigger class="h-8 bg-background/40 text-xs"><SelectValue placeholder="风险等级" /></SelectTrigger><SelectContent><SelectItem value="all">全部等级</SelectItem><SelectItem value="high">高风险</SelectItem><SelectItem value="medium">中风险</SelectItem><SelectItem value="low">低风险</SelectItem><SelectItem value="review_required">待复核</SelectItem></SelectContent></Select><Select v-model="sortBy"><SelectTrigger class="h-8 bg-background/40 text-xs"><SelectValue placeholder="排序" /></SelectTrigger><SelectContent><SelectItem value="level">等级优先</SelectItem><SelectItem value="score">分数优先</SelectItem></SelectContent></Select></div><RiskListTable :risks="filteredRisks" :selected-risk-id="selectedRiskId" :hovered-risk-id="hoveredRiskId" @row-click="handleRiskSelection($event.id, 'list')" @row-hover="spatialSelection.hoverRisk($event)" /></section>
      <div class="min-w-0 min-h-[560px] xl:min-h-0"><MultiModalEvidenceCanvas :risks="filteredRisks" :zones="allZones" :selected-risk-id="selectedRiskId" :hovered-risk-id="hoveredRiskId" :selected-risk="selectedRisk" :active-view="activeView" :zone-id="zoneId" :visualization="agentVisualization" :spatial="agentSnapshot.spatial" :point-cloud-url="pointCloudArtifact?.downloadUrl" :point-cloud-title="pointCloudArtifact?.title" :point-mask-url="selectedPointMaskArtifact?.downloadUrl" :point-mask-array-name="selectedPointMaskArtifact?.role === 'relation_mask' ? 'relation_mask' : 'target_mask'" :point-probabilities-url="selectedPointProbabilityArtifact?.downloadUrl" :semantic-labels-url="semanticLabelsArtifact?.downloadUrl" :semantic-classes="semanticClasses" :loading="isSynchronizing && !agentVisualization?.ortho" @risk-click="handleRiskSelection($event, 'map')" @risk-hover="spatialSelection.hoverRisk($event)" @view-change="spatialSelection.setView($event)" /></div>
      <div v-if="selectedRisk" class="min-h-[640px] xl:min-h-0"><RiskDetailCard :risk="selectedRisk" :agent-snapshot="agentSnapshot" :agent-context="selectedRiskContext" @create-workorder="handleCreateWorkorder" @mark-review="handleMarkReview" /></div><div v-else class="flex min-h-[360px] items-center justify-center rounded-[18px] border border-border/60 bg-card/35 text-sm text-muted-foreground">当前筛选条件下暂无风险</div>
    </div></div>
  </div>
  <div v-else-if="isClientReady" class="flex h-full items-center justify-center bg-background"><div class="max-w-md space-y-4 rounded-2xl border border-border/60 bg-card/45 p-8 text-center"><SafeIcon name="ShieldQuestion" :size="40" class="mx-auto text-muted-foreground" /><h1 class="text-lg font-semibold">当前任务没有可研判的 Agent 成果</h1><p class="text-sm leading-6 text-muted-foreground">请返回任务指挥台创建并完成动态分析，风险、证据和质量结论生成后可进入本页面。</p><Button @click="window.location.href = './task-studio.html'">返回任务指挥台</Button></div></div>
  <div v-else class="flex h-full items-center justify-center bg-background"><div class="flex flex-col items-center gap-4 text-sm text-muted-foreground"><div class="h-10 w-10 animate-spin rounded-full border-2 border-cyan-300/20 border-t-cyan-300" /><span>正在准备风险研判结果</span></div></div>
</template>

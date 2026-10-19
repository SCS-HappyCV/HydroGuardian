<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { remoteAgentApi } from '@/api/remote-agent-api'
import type { RemoteAuditReport } from '@/lib/remote-audit-report'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Button } from '@/components/ui/button'

const report = ref<RemoteAuditReport | null>(null)
const loading = ref(true)
const error = ref('')
const digestVerified = ref(false)

const statusLabels: Record<string, string> = {
  succeeded: '执行成功', blocked_expert: '专家受限', failed: '执行失败', cancelled: '已取消',
  executing: '执行中', planning: '规划中', queued_execution: '等待执行', queued_planning: '等待规划',
}
const toolLabels: Record<string, string> = {
  image_change_detection: '前后影像变化检测', point_semantic_segmentation: '点云语义分割',
  language_guided_point_segmentation: '语言引导点云定位',
  geometry_relation_analysis: '空间几何关系分析', result_quality_verification: '结果质量验证',
}

const steps = computed(() => report.value?.execution.steps || [])
const candidates = computed(() => report.value?.findings.risk_candidates || [])
const artifacts = computed(() => report.value?.artifacts || [])
const workorders = computed(() => report.value?.workorders || [])
const completedSteps = computed(() => steps.value.filter((item) => item.status === 'succeeded').length)
const spatial = computed(() => report.value?.findings.spatial_context as Record<string, any> | undefined)
const spatialPrimary = computed(() => {
  const assets = spatial.value?.assets
  if (!assets || typeof assets !== 'object') return undefined
  return assets.after_image_path || assets.image_path || assets.point_cloud_path || Object.values(assets)[0]
})
const geographic = computed(() => spatialPrimary.value?.extent?.geographic)

function formatDate(value?: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function formatBytes(value?: number | null): string {
  if (!value) return '—'
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 ** 2).toFixed(1)} MB`
}

function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  return `{${Object.keys(value as Record<string, unknown>).sort().map((key) => `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`).join(',')}}`
}

function normalizeForDigest(value: unknown): unknown {
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return String(value)
    return value.toFixed(15).replace(/0+$/, '').replace(/\.$/, '')
  }
  if (Array.isArray(value)) return value.map(normalizeForDigest)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, normalizeForDigest(item)]))
  return value
}

async function verifyDigest(value: RemoteAuditReport) {
  const { integrity, ...document } = value
  const bytes = new TextEncoder().encode(canonical(normalizeForDigest(document)))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const hex = [...new Uint8Array(digest)].map((item) => item.toString(16).padStart(2, '0')).join('')
  digestVerified.value = hex === integrity.digest
}

async function loadReport() {
  const params = new URLSearchParams(window.location.search)
  let jobId = params.get('jobId') || ''
  const workorderId = params.get('workorderId')
  if (!jobId && workorderId) {
    try { jobId = (await remoteAgentApi.getWorkorder(workorderId)).job_id } catch {}
  }
  if (!jobId) {
    error.value = '缺少可生成报告的真实任务标识'
    loading.value = false
    return
  }
  try {
    report.value = await remoteAgentApi.getAuditReport(jobId)
    await verifyDigest(report.value)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '审计报告生成失败'
  } finally {
    loading.value = false
  }
}

function downloadJson() {
  if (!report.value) return
  const blob = new Blob([JSON.stringify(report.value, null, 2)], { type: 'application/json;charset=utf-8' })
  const anchor = document.createElement('a')
  anchor.href = URL.createObjectURL(blob)
  anchor.download = `HydroGuardian审计报告-${report.value.subject.job_id}.json`
  anchor.click()
  URL.revokeObjectURL(anchor.href)
  toast.success('审计原始数据已导出')
}

function printReport() {
  window.print()
}

onMounted(loadReport)
</script>

<template>
  <div class="audit-shell min-h-screen bg-[#060d17] text-slate-100">
    <header class="audit-toolbar sticky top-0 z-50 border-b border-white/10 bg-[#07111f]/90 px-5 py-3 backdrop-blur-xl">
      <div class="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3"><button type="button" class="grid h-9 w-9 place-items-center rounded-lg border border-white/10 text-slate-300 hover:bg-white/5" @click="history.back()"><SafeIcon name="ArrowLeft" :size="16" /></button><div><div class="text-sm font-semibold text-white">可审计巡查报告</div><div class="mt-0.5 text-[10px] text-slate-400">任务事实、证据产物与闭环记录统一归档</div></div></div>
        <div class="flex items-center gap-2"><span v-if="report" class="mr-2 hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] sm:flex" :class="digestVerified ? 'border-emerald-300/20 bg-emerald-300/10 text-emerald-200' : 'border-rose-300/20 bg-rose-300/10 text-rose-200'"><SafeIcon :name="digestVerified ? 'BadgeCheck' : 'ShieldAlert'" :size="12" />{{ digestVerified ? '完整性校验通过' : '完整性校验异常' }}</span><Button variant="outline" size="sm" class="gap-2 border-white/10" :disabled="!report" @click="downloadJson"><SafeIcon name="Braces" :size="14" />导出审计数据</Button><Button size="sm" class="gap-2 bg-cyan-500 text-slate-950 hover:bg-cyan-400" :disabled="!report" @click="printReport"><SafeIcon name="FileDown" :size="14" />打印 / 导出 PDF</Button></div>
      </div>
    </header>

    <main v-if="loading" class="grid min-h-[75vh] place-items-center"><div class="text-center"><SafeIcon name="LoaderCircle" :size="36" class="mx-auto animate-spin text-cyan-300" /><p class="mt-3 text-sm text-slate-300">正在汇集后端审计记录</p></div></main>
    <main v-else-if="error" class="grid min-h-[75vh] place-items-center"><div class="max-w-md text-center"><SafeIcon name="FileWarning" :size="42" class="mx-auto text-rose-300" /><h1 class="mt-4 text-lg font-semibold">报告暂时无法生成</h1><p class="mt-2 text-sm text-slate-400">{{ error }}</p></div></main>

    <main v-else-if="report" class="audit-document mx-auto max-w-[1180px] space-y-5 px-4 py-8 sm:px-6">
      <section class="audit-cover relative overflow-hidden rounded-3xl border border-cyan-300/15 bg-[linear-gradient(145deg,#0d2b3b,#091726_48%,#07111f)] p-7 shadow-2xl shadow-black/30 sm:p-10">
        <div class="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-cyan-400/10 blur-3xl" />
        <div class="relative flex flex-wrap items-start justify-between gap-8"><div><div class="flex items-center gap-3"><span class="grid h-12 w-12 place-items-center rounded-2xl border border-cyan-200/20 bg-cyan-300/10 text-cyan-200"><SafeIcon name="Waves" :size="25" /></span><div><div class="text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-300">HYDROGUARDIAN AUDIT DOSSIER</div><h1 class="mt-1 text-2xl font-bold text-white sm:text-3xl">水利智能巡查审计报告</h1></div></div><p class="mt-5 max-w-2xl text-sm leading-7 text-slate-300">{{ report.task?.input_text || report.job.submission.query }}</p></div><div class="rounded-2xl border border-white/10 bg-black/20 p-4 text-right"><div class="text-[9px] uppercase tracking-[0.18em] text-slate-500">报告编号</div><div class="mt-1 font-mono text-xs text-cyan-100">{{ report.subject.job_id }}</div><div class="mt-3 text-[9px] text-slate-500">生成时间</div><div class="mt-1 text-xs text-slate-300">{{ formatDate(report.generated_at) }}</div></div></div>
        <div class="relative mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-5"><div v-for="metric in [{ label: '执行状态', value: statusLabels[report.subject.status] || report.subject.status, icon: 'Activity' }, { label: '专家步骤', value: `${completedSteps}/${steps.length}`, icon: 'Workflow' }, { label: '风险候选', value: candidates.length, icon: 'ShieldAlert' }, { label: '证据产物', value: artifacts.length, icon: 'PackageCheck' }, { label: '闭环工单', value: workorders.length, icon: 'ClipboardCheck' }]" :key="metric.label" class="rounded-xl border border-white/10 bg-white/[0.035] p-3"><div class="flex items-center gap-1.5 text-[10px] text-slate-400"><SafeIcon :name="metric.icon" :size="12" class="text-cyan-300" />{{ metric.label }}</div><strong class="mt-2 block text-lg text-white">{{ metric.value }}</strong></div></div>
      </section>

      <section class="audit-section grid gap-5 lg:grid-cols-[1.15fr_.85fr]">
        <article class="rounded-2xl border border-white/10 bg-[#0a1522] p-5"><div class="audit-heading"><SafeIcon name="FileInput" :size="16" />任务与追踪标识</div><dl class="mt-4 grid gap-3 text-xs sm:grid-cols-2"><div><dt>任务名称</dt><dd>{{ report.task?.name || '智能巡查任务' }}</dd></div><div><dt>任务状态</dt><dd>{{ statusLabels[report.subject.status] || report.subject.status }}</dd></div><div><dt>Request ID</dt><dd class="font-mono">{{ report.subject.request_id }}</dd></div><div><dt>Trace ID</dt><dd class="font-mono">{{ report.subject.trace_id }}</dd></div><div><dt>创建时间</dt><dd>{{ formatDate(report.job.created_at) }}</dd></div><div><dt>最后更新</dt><dd>{{ formatDate(report.job.updated_at) }}</dd></div></dl></article>
        <article class="rounded-2xl border border-white/10 bg-[#0a1522] p-5"><div class="audit-heading"><SafeIcon name="MapPinned" :size="16" />空间基准</div><div v-if="geographic" class="mt-4"><div class="font-mono text-xl font-semibold text-cyan-100">{{ Number(geographic.center_lon).toFixed(6) }}, {{ Number(geographic.center_lat).toFixed(6) }}</div><p class="mt-2 text-xs text-slate-400">{{ spatialPrimary?.crs?.name || 'CGCS2000' }} · EPSG:{{ spatialPrimary?.crs?.code || '—' }}</p><div class="mt-4 grid grid-cols-2 gap-2 text-[10px]"><span class="rounded-lg bg-white/[0.04] p-2">西 {{ geographic.west }}</span><span class="rounded-lg bg-white/[0.04] p-2">东 {{ geographic.east }}</span><span class="rounded-lg bg-white/[0.04] p-2">南 {{ geographic.south }}</span><span class="rounded-lg bg-white/[0.04] p-2">北 {{ geographic.north }}</span></div></div><p v-else class="mt-4 text-xs text-slate-500">本次任务未形成可审计空间基准。</p></article>
      </section>

      <section class="audit-section rounded-2xl border border-white/10 bg-[#0a1522] p-5"><div class="flex items-center justify-between"><div class="audit-heading"><SafeIcon name="GitBranch" :size="16" />动态专家执行路径</div><span class="text-[10px] text-slate-500">{{ steps.length }} 个步骤</span></div><div class="mt-5 space-y-3"><article v-for="(step, index) in steps" :key="step.step_id" class="grid gap-3 rounded-xl border border-white/[0.07] bg-white/[0.025] p-4 sm:grid-cols-[44px_1fr_auto]"><span class="grid h-9 w-9 place-items-center rounded-full text-xs font-bold" :class="step.status === 'succeeded' ? 'bg-emerald-300/15 text-emerald-200' : 'bg-amber-300/15 text-amber-200'">{{ index + 1 }}</span><div><h3 class="text-xs font-semibold text-white">{{ toolLabels[step.tool] || step.tool }}</h3><p class="mt-1 text-[10px] text-slate-400">{{ step.phase || '专家执行' }} · {{ step.worker_id || '等待专家节点' }}</p></div><div class="text-right"><span class="rounded-full border border-white/10 px-2 py-1 text-[9px]">{{ step.status }}</span><p class="mt-2 text-[9px] text-slate-500">{{ formatDate(step.updated_at) }}</p></div></article><p v-if="!steps.length" class="py-6 text-center text-xs text-slate-500">本次记录中没有专家执行步骤</p></div></section>

      <section class="audit-section rounded-2xl border border-white/10 bg-[#0a1522] p-5"><div class="audit-heading"><SafeIcon name="ScanSearch" :size="16" />风险研判结论</div><div class="mt-5 grid gap-3 md:grid-cols-2"><article v-for="(candidate, index) in candidates" :key="String(candidate.candidate_id || index)" class="rounded-xl border border-amber-300/15 bg-amber-300/[0.04] p-4"><div class="flex items-center justify-between gap-3"><h3 class="text-sm font-semibold text-white">{{ candidate.title || `风险候选 ${index + 1}` }}</h3><span class="rounded-full bg-amber-300/10 px-2 py-1 text-[9px] text-amber-200">{{ candidate.risk_level || '待复核' }}</span></div><p class="mt-3 text-xs leading-6 text-slate-300">{{ candidate.summary }}</p><div class="mt-3 flex flex-wrap gap-2 text-[9px] text-slate-400"><span>类型 {{ candidate.risk_type }}</span><span>证据强度 {{ candidate.score }}</span><span v-if="candidate.review_required">需要业务确认</span></div></article><p v-if="!candidates.length" class="col-span-full py-8 text-center text-xs text-slate-500">本次专家结果未形成风险候选</p></div></section>

      <section class="audit-section overflow-hidden rounded-2xl border border-white/10 bg-[#0a1522]"><div class="flex items-center justify-between px-5 py-4"><div class="audit-heading"><SafeIcon name="DatabaseZap" :size="16" />证据产物登记簿</div><span class="text-[10px] text-slate-500">稳定资产 ID，不记录临时下载地址</span></div><div class="overflow-x-auto"><table class="w-full min-w-[820px] text-left text-[10px]"><thead class="border-y border-white/[0.07] bg-white/[0.025] text-slate-400"><tr><th>资产 ID</th><th>文件</th><th>类型</th><th>大小</th><th>SHA-256</th></tr></thead><tbody><tr v-for="artifact in artifacts" :key="artifact.artifact_id" class="border-b border-white/[0.05]"><td class="font-mono text-cyan-200">{{ artifact.artifact_id }}</td><td>{{ artifact.object_key?.split('/').at(-1) || '目录中暂不可用' }}</td><td>{{ artifact.media_type || '—' }}</td><td>{{ formatBytes(artifact.size_bytes) }}</td><td class="font-mono text-slate-400">{{ artifact.sha256 || '未提供' }}</td></tr></tbody></table></div></section>

      <section class="audit-section rounded-2xl border border-white/10 bg-[#0a1522] p-5"><div class="audit-heading"><SafeIcon name="ClipboardCheck" :size="16" />工单闭环审计</div><div class="mt-5 space-y-4"><article v-for="order in workorders" :key="order.workorder_id" class="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4"><div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="text-sm font-semibold text-white">{{ order.title }}</h3><p class="mt-1 font-mono text-[9px] text-slate-500">{{ order.workorder_id }}</p></div><span class="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2.5 py-1 text-[9px] text-cyan-200">{{ order.status }}</span></div><div class="mt-4 grid gap-2 sm:grid-cols-4"><div v-for="event in order.timeline" :key="event.event_id" class="rounded-lg border border-white/[0.06] p-2"><div class="text-[9px] font-semibold text-slate-200">{{ event.action }}</div><div class="mt-1 text-[9px] text-slate-500">{{ formatDate(event.created_at) }}</div></div></div><div class="mt-3 text-[10px] text-slate-400">证据 {{ order.evidence.length }} 项 · 复核 {{ order.reviews.length }} 次 · 版本 {{ order.version }}</div></article><p v-if="!workorders.length" class="py-6 text-center text-xs text-slate-500">当前任务尚未生成处置工单</p></div></section>

      <footer class="audit-section rounded-2xl border border-emerald-300/15 bg-emerald-300/[0.04] p-5"><div class="flex flex-wrap items-start justify-between gap-5"><div class="flex items-start gap-3"><span class="grid h-10 w-10 place-items-center rounded-xl bg-emerald-300/10 text-emerald-200"><SafeIcon name="ShieldCheck" :size="20" /></span><div><h2 class="text-sm font-semibold text-white">报告完整性凭据</h2><p class="mt-1 text-[10px] text-slate-400">{{ report.integrity.scope }}</p></div></div><span class="rounded-full px-2.5 py-1 text-[9px] font-semibold" :class="digestVerified ? 'bg-emerald-300/15 text-emerald-200' : 'bg-rose-300/15 text-rose-200'">{{ digestVerified ? '浏览器复算一致' : '复算不一致' }}</span></div><div class="mt-4 break-all rounded-xl border border-white/[0.07] bg-black/20 p-3 font-mono text-[10px] leading-5 text-emerald-100">SHA-256 {{ report.integrity.digest }}</div><div class="mt-3 flex flex-wrap gap-4 text-[9px] text-slate-500"><span>事件记录 {{ report.integrity.event_count }}</span><span>资产记录 {{ report.integrity.artifact_count }}</span><span>Schema {{ report.schema_version }}</span></div></footer>
    </main>
  </div>
</template>

<style scoped>
.audit-heading { display: flex; align-items: center; gap: .5rem; font-size: .8rem; font-weight: 600; color: white; }
dl dt { color: rgb(100 116 139); font-size: .625rem; }
dl dd { margin-top: .35rem; color: rgb(226 232 240); overflow-wrap: anywhere; }
th, td { padding: .75rem 1rem; vertical-align: top; }

@media print {
  :global(body) { background: white !important; color: #0f172a !important; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  .audit-shell { background: white !important; color: #0f172a !important; }
  .audit-toolbar { display: none !important; }
  .audit-document { max-width: none !important; padding: 0 !important; }
  .audit-cover, .audit-section { break-inside: avoid; box-shadow: none !important; }
  .audit-section { margin-top: 12px !important; }
  table { break-inside: auto; }
  tr { break-inside: avoid; }
}
</style>

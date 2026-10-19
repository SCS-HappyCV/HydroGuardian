<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentPresentationSnapshot, AgentQualityCheckStatus, AgentQualityReportView, AgentQualityVerdict } from '@/lib/agent-presentation-types'

const props = defineProps<{ snapshot: AgentPresentationSnapshot }>()
const quality = computed(() => props.snapshot.quality)
const reports = computed(() => quality.value.reports || [])
const passedChecks = computed(() => quality.value.checks.filter((item) => item.status === 'passed').length)
const issueChecks = computed(() => quality.value.checks.filter((item) => item.status === 'warning' || item.status === 'failed').length)
const abstentionRecommended = computed(() => reports.value.some((item) => item.abstentionRecommended))

const verdictLabels: Record<AgentQualityVerdict, string> = {
  passed: '质量验证通过',
  limited: '结果存在限制',
  review_required: '建议人工复核',
  unavailable: '等待质量验证',
}

function verdictClass(verdict: AgentQualityVerdict) {
  if (verdict === 'passed') return 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200'
  if (verdict === 'limited') return 'border-amber-400/20 bg-amber-400/10 text-amber-100'
  if (verdict === 'review_required') return 'border-rose-400/20 bg-rose-400/10 text-rose-100'
  return 'border-white/10 bg-white/5 text-muted-foreground'
}

function checkClass(status: AgentQualityCheckStatus) {
  if (status === 'passed') return 'bg-emerald-400'
  if (status === 'warning') return 'bg-amber-400'
  if (status === 'failed') return 'bg-rose-400'
  return 'bg-slate-400'
}

function checkLabel(status: AgentQualityCheckStatus) {
  return status === 'passed' ? '通过' : status === 'warning' ? '受限' : status === 'failed' ? '未通过' : '待确认'
}

function score(value?: number) {
  return value === undefined ? '—' : `${Math.round(value * 100)} 分`
}

function measurement(value: number, format: 'count' | 'percent' | 'number') {
  if (format === 'percent') return `${(value * 100).toFixed(value > 0 && value < 0.01 ? 2 : 1)}%`
  if (format === 'count') return Math.round(value).toLocaleString('zh-CN')
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 3 })
}

function overlayFor(report: AgentQualityReportView) {
  return props.snapshot.evidence.artifacts.find((artifact) => artifact.role === 'diagnostic_overlay' && report.artifactRefs.includes(artifact.artifactId))
}
</script>

<template>
  <section v-if="reports.length" class="overflow-hidden rounded-2xl border border-emerald-400/20 bg-gradient-to-br from-emerald-400/[0.07] via-card/60 to-cyan-400/[0.04]">
    <div class="flex flex-col gap-4 border-b border-white/[0.07] p-5 sm:flex-row sm:items-start sm:justify-between">
      <div class="flex items-start gap-3">
        <div class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-emerald-400/10 text-emerald-300"><SafeIcon name="ShieldCheck" :size="21" /></div>
        <div><p class="text-[10px] uppercase tracking-[0.18em] text-emerald-300">RESULT QUALITY ASSURANCE</p><h2 class="mt-1 text-base font-semibold text-foreground">结果质量验证</h2><p class="mt-1 text-xs leading-5 text-muted-foreground">对专家产物进行结构、数值和空间一致性检查，并给出是否继续自动研判的建议</p></div>
      </div>
      <span class="w-fit rounded-full border px-3 py-1.5 text-[10px] font-medium" :class="verdictClass(quality.verdict)">{{ verdictLabels[quality.verdict] }}</span>
    </div>

    <div class="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4">
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">任务质量分</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ score(quality.confidence) }}</p><div class="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.07]"><div class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400" :style="{ width: `${Math.max((quality.confidence || 0) * 100, 2)}%` }" /></div></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">已验证专家结果</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ reports.length }} 项</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">通过检查</p><p class="mt-1.5 text-sm font-semibold text-emerald-200">{{ passedChecks }} 项</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">限制或异常</p><p class="mt-1.5 text-sm font-semibold" :class="issueChecks ? 'text-amber-200' : 'text-card-foreground'">{{ issueChecks }} 项</p></div>
    </div>

    <div class="space-y-4 px-5 pb-5">
      <article v-for="report in reports" :key="report.reportId" class="overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.025]">
        <div class="flex flex-col gap-3 border-b border-white/[0.06] px-4 py-3 sm:flex-row sm:items-center sm:justify-between"><div><h3 class="text-xs font-medium text-card-foreground">{{ report.sourceToolLabel }}</h3><p class="mt-1 text-[10px] text-muted-foreground">确定性质量检查 · {{ report.checks.length }} 个检查项 · {{ report.artifactRefs.length }} 项可追溯产物</p></div><div class="flex items-center gap-2"><span class="text-xs font-semibold text-emerald-200">{{ score(report.score) }}</span><span class="rounded-full border px-2.5 py-1 text-[9px]" :class="verdictClass(report.verdict)">{{ verdictLabels[report.verdict] }}</span></div></div>
        <div class="grid gap-4 p-4" :class="overlayFor(report)?.previewUrl ? 'lg:grid-cols-[1fr_280px]' : ''">
          <div class="space-y-4">
            <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3"><div v-for="check in report.checks" :key="check.checkId" class="rounded-lg border border-white/[0.06] bg-black/10 p-3"><div class="flex items-center justify-between gap-2"><span class="text-[10px] font-medium text-card-foreground">{{ check.label }}</span><span class="flex items-center gap-1.5 text-[9px] text-muted-foreground"><span class="h-1.5 w-1.5 rounded-full" :class="checkClass(check.status)" />{{ checkLabel(check.status) }}</span></div><p class="mt-1.5 text-[9px] leading-4 text-muted-foreground">{{ check.summary }}</p></div></div>
            <div v-if="report.measurements.length" class="flex flex-wrap gap-2"><div v-for="item in report.measurements" :key="item.key" class="rounded-lg border border-white/[0.06] bg-black/10 px-3 py-2 text-[10px]"><span class="text-muted-foreground">{{ item.label }}</span><span class="ml-2 font-medium text-emerald-200">{{ measurement(item.value, item.format) }}</span></div></div>
          </div>
          <div v-if="overlayFor(report)?.previewUrl" class="overflow-hidden rounded-lg border border-white/[0.07] bg-black/10"><img :src="overlayFor(report)?.previewUrl" :alt="`${report.sourceToolLabel}质量诊断图`" class="h-full min-h-40 w-full object-contain" /></div>
        </div>
      </article>

      <div v-if="abstentionRecommended" class="flex items-start gap-2 rounded-xl border border-rose-400/20 bg-rose-400/[0.07] p-3 text-[10px] leading-4 text-rose-100"><SafeIcon name="ShieldAlert" :size="15" class="mt-0.5 shrink-0" /><span>质量专家建议暂停自动判定。本次结果应保留原始证据并进入人工复核，不能直接形成自动风险结论。</span></div>
      <div v-else class="flex items-start gap-2 rounded-xl border border-cyan-400/15 bg-cyan-400/[0.05] p-3 text-[10px] leading-4 text-muted-foreground"><SafeIcon name="BadgeInfo" :size="15" class="mt-0.5 shrink-0 text-cyan-300" /><span>{{ quality.recommendedAction }} 质量验证关注产物结构、数值范围和一致性，不代表业务风险成立，也不替代语义正确性与现场复核。</span></div>
    </div>
  </section>
</template>

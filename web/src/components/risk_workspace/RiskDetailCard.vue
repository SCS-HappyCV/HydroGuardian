<script setup lang="ts">
import { computed } from 'vue'
import type { RiskEventData } from '@/data/RiskEventData'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'
import type { AgentRiskContext } from '@/lib/agent-risk-presentation'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/common/StatusBadge.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import FieldLocationPanel from '@/components/common/FieldLocationPanel.vue'

const props = defineProps<{
  risk: RiskEventData
  agentSnapshot: AgentPresentationSnapshot
  agentContext?: AgentRiskContext
}>()

defineEmits<{ 'create-workorder': []; 'mark-review': [] }>()

const confidence = computed(() => Math.round((props.agentSnapshot.quality.confidence ?? props.risk.score / 100) * 100))
const uncertainty = computed(() => Math.round((props.agentSnapshot.quality.uncertainty ?? (1 - props.risk.score / 100)) * 100))
const draft = computed(() => props.agentSnapshot.business.workOrders.find((item) => item.riskId === props.risk.id))
const recommendation = computed(() => draft.value?.recommendedAction || props.agentSnapshot.business.recommendations.find((item) => item.includes(props.agentContext?.region?.label?.split(' ')[0] || '')) || props.agentSnapshot.business.recommendations[0])
const qualityGateLabel = computed(() => props.risk.qualityGate?.automationAllowed ? '质量门控通过' : '仅限人工复核')
const sourceLabel = computed(() => ({ image_change_detection: '前后时相变化检测', geometry_relation_analysis: '空间几何关系分析' }[props.risk.sourceTool || ''] || '真实专家结果'))
const ruleLabel = computed(() => ({ 'change-region-present-v1': '变化区域存在规则', 'geometry-near-match-v1': '邻近关系命中规则', 'geometry-above-match-v1': '高程关系命中规则' }[props.risk.ruleId] || props.risk.ruleId))

function checkTone(status: 'passed' | 'warning' | 'failed' | 'unknown') {
  if (status === 'passed') return 'border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-300'
  if (status === 'warning') return 'border-amber-400/20 bg-amber-400/[0.06] text-amber-300'
  if (status === 'failed') return 'border-destructive/25 bg-destructive/[0.06] text-destructive'
  return 'border-border/50 bg-muted/15 text-muted-foreground'
}
</script>

<template>
  <aside class="flex h-full flex-col overflow-hidden rounded-[18px] border border-border/60 bg-card/45">
    <div class="border-b border-border/50 bg-gradient-to-br from-primary/[0.08] to-transparent p-4">
      <div class="flex items-start justify-between gap-3"><div class="min-w-0"><div class="mb-2 flex items-center gap-2"><span class="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">Agent 风险候选</span><StatusBadge :status="risk.level" size="sm" /></div><h2 class="text-base font-semibold leading-snug">{{ risk.title }}</h2></div><div class="shrink-0 text-right"><div class="text-[10px] text-muted-foreground">证据强度</div><div class="mt-1 text-3xl font-bold">{{ risk.score }}</div></div></div>
      <p class="mt-3 text-xs leading-relaxed text-muted-foreground">{{ risk.description }}</p>
      <div class="mt-3 flex flex-wrap gap-2 text-[9px]"><span class="rounded-full border border-cyan-400/15 bg-cyan-400/[0.06] px-2.5 py-1 text-cyan-200">来源：{{ sourceLabel }}</span><span class="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-muted-foreground">规则：{{ ruleLabel }}</span></div>
      <div class="mt-4 grid grid-cols-2 gap-2"><div class="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.06] p-2.5"><div class="text-[10px] text-muted-foreground">综合置信度</div><div class="mt-1 flex items-end justify-between"><strong class="text-lg text-cyan-300">{{ confidence }}%</strong><SafeIcon name="BadgeCheck" :size="15" class="mb-1 text-cyan-400" /></div></div><div class="rounded-xl border border-violet-400/15 bg-violet-400/[0.06] p-2.5"><div class="text-[10px] text-muted-foreground">结果不确定性</div><div class="mt-1 flex items-end justify-between"><strong class="text-lg text-violet-300">{{ uncertainty }}%</strong><SafeIcon name="ShieldQuestion" :size="15" class="mb-1 text-violet-400" /></div></div></div>
    </div>

    <div class="flex-1 space-y-5 overflow-y-auto p-4">
      <FieldLocationPanel :location="risk.location" :label="risk.title" compact />
      <section><div class="mb-3 flex items-center justify-between"><h3 class="flex items-center gap-2 text-xs font-semibold"><SafeIcon name="PackageCheck" :size="14" class="text-cyan-400" />关联证据产物</h3><span class="text-[10px] text-muted-foreground">{{ agentContext?.artifacts.length || 0 }} 项</span></div><div class="space-y-2"><article v-for="artifact in agentContext?.artifacts" :key="artifact.artifactId" class="rounded-xl border border-border/40 bg-muted/15 p-3"><div class="flex items-center gap-2"><span class="grid h-7 w-7 place-items-center rounded-lg bg-cyan-400/10 text-cyan-300"><SafeIcon :name="artifact.mediaType.includes('image') ? 'Image' : 'FileJson'" :size="14" /></span><div class="min-w-0"><p class="truncate text-xs font-medium">{{ artifact.title }}</p><p class="mt-0.5 text-[10px] text-muted-foreground">{{ artifact.role }} · 第 {{ artifact.availableAtStep }} 步生成</p></div></div></article><div v-if="!agentContext?.artifacts.length" class="rounded-xl border border-dashed border-border/50 p-4 text-center text-xs text-muted-foreground">该风险尚无可用证据产物</div></div></section>

      <section><div class="mb-3 flex items-center justify-between"><h3 class="flex items-center gap-2 text-xs font-semibold"><SafeIcon name="ListChecks" :size="14" class="text-violet-300" />质量验证</h3><span class="text-[10px] text-muted-foreground">{{ agentSnapshot.quality.checks.length }} 项检查</span></div><div class="space-y-2"><article v-for="check in agentSnapshot.quality.checks" :key="check.checkId" class="rounded-xl border p-3" :class="checkTone(check.status)"><div class="flex items-center justify-between gap-2"><span class="text-xs font-medium">{{ check.label }}</span><SafeIcon :name="check.status === 'passed' ? 'CheckCircle2' : check.status === 'warning' ? 'AlertTriangle' : 'CircleHelp'" :size="14" /></div><p class="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{{ check.summary }}</p></article></div></section>

      <section v-if="risk.reviewRequired || agentSnapshot.quality.warnings.length" class="rounded-xl border border-violet-400/20 bg-violet-400/[0.06] p-3"><div class="flex items-center justify-between gap-2"><h3 class="flex items-center gap-2 text-xs font-semibold text-violet-200"><SafeIcon name="ShieldQuestion" :size="14" />人工复核原因</h3><span class="rounded-full border border-violet-300/20 px-2 py-1 text-[9px] text-violet-200">{{ qualityGateLabel }}</span></div><p class="mt-2 text-[11px] leading-relaxed text-muted-foreground">{{ agentSnapshot.quality.warnings.join('；') || agentContext?.region?.summary || '风险候选需要结合正式业务规则与现场证据确认。' }}</p><p class="mt-2 text-[10px] text-violet-300/80">质量门控只判断专家产物是否可用；风险性质和处置等级必须经过业务确认。</p></section>

      <section class="rounded-xl border border-primary/20 bg-primary/[0.05] p-3"><div class="flex items-center justify-between gap-2"><h3 class="flex items-center gap-2 text-xs font-semibold"><SafeIcon name="Sparkles" :size="14" class="text-cyan-300" />Agent 处置建议</h3><span class="rounded-full bg-primary/10 px-2 py-1 text-[10px] text-primary">{{ draft ? '已规划工单' : '建议复核' }}</span></div><p class="mt-3 text-xs leading-relaxed">{{ recommendation || '补充现场证据后再决定后续处置。' }}</p><p class="mt-2 text-[11px] text-muted-foreground">{{ agentContext?.region?.summary }}</p></section>
    </div>

    <div class="grid grid-cols-2 gap-2 border-t border-border/50 bg-background/50 p-3"><Button variant="outline" size="sm" class="gap-1.5" :disabled="risk.status === 'review_required'" @click="$emit('mark-review')"><SafeIcon :name="risk.status === 'review_required' ? 'CheckCircle2' : 'UserRoundCheck'" :size="14" />{{ risk.status === 'review_required' ? '已进入人工复核' : '转人工复核' }}</Button><Button size="sm" class="gap-1.5 bg-primary" @click="$emit('create-workorder')"><SafeIcon :name="risk.workorderId ? 'ExternalLink' : 'ClipboardPlus'" :size="14" />{{ risk.workorderId ? '查看处置工单' : '生成处置工单' }}</Button></div>
  </aside>
</template>

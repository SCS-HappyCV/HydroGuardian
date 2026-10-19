<script setup lang="ts">
import { computed } from 'vue'
import type { RiskEventData } from '@/data/RiskEventData'
import type { WorkorderData } from '@/data/WorkorderData'
import type { WorkorderEvidenceData } from '@/data/WorkorderEvidenceData'
import type { TaskData } from '@/data/TaskData'
import { buildRiskEvidenceProfile } from '@/lib/risk-evidence'
import SafeIcon from '@/components/common/SafeIcon.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'

interface Props {
  workorder: WorkorderData
  risk?: RiskEventData | null
  task?: TaskData | null
  evidence?: WorkorderEvidenceData[]
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  risk: null,
  task: null,
  evidence: () => [],
  compact: false,
})

const profile = computed(() => props.risk ? buildRiskEvidenceProfile(props.risk) : null)
const evidenceItems = computed(() => {
  if (props.evidence.length) return props.evidence.slice(0, props.compact ? 2 : 3)
  return [
    { id: 'fallback-image', title: '正射影像证据', content: props.risk?.evidenceSummary || '风险区域已完成空间定位。', evidenceType: 'before' as const, orderId: props.workorder.id, createdAt: props.workorder.createdAt },
    { id: 'fallback-geometry', title: '点云几何证据', content: '几何形态与目标风险特征一致。', evidenceType: 'note' as const, orderId: props.workorder.id, createdAt: props.workorder.createdAt },
  ]
})

function evidenceIcon(type: string): string {
  if (type === 'after') return 'Camera'
  if (type === 'note') return 'Box'
  return 'Image'
}
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-cyan-400/20 bg-gradient-to-br from-[#0b2131] via-[#0a1828] to-[#08121f]">
    <div class="grid gap-4 p-4" :class="compact ? 'grid-cols-1 sm:grid-cols-[150px_minmax(0,1fr)]' : 'lg:grid-cols-[240px_1fr]'">
      <div class="relative min-h-[130px] overflow-hidden rounded-xl border border-white/10 bg-[linear-gradient(150deg,#183d3c_0%,#286b70_32%,#b18f5e_33%,#41583b_58%,#172e2a_100%)]">
        <svg class="absolute inset-0 h-full w-full" viewBox="0 0 400 240" preserveAspectRatio="none" aria-label="风险区域缩略图">
          <path d="M-30 35 C70 8 105 83 185 73 C263 64 304 14 430 40 L430 112 C335 86 279 141 194 132 C107 123 68 81 -30 117Z" fill="#2b8195" fill-opacity=".85" />
          <path d="M92 176 C138 137 218 145 268 174 C289 187 282 209 253 217 C199 230 124 217 92 195Z" fill="#ffb85c" fill-opacity=".27" stroke="#ffd06b" stroke-width="3" stroke-dasharray="7 5" />
          <path d="M108 179 C151 155 214 159 249 180" fill="none" stroke="#ff716a" stroke-width="5" />
        </svg>
        <div class="absolute left-3 top-3 rounded-lg border border-white/10 bg-black/45 px-2 py-1 text-[10px] text-cyan-100 backdrop-blur">
          AI 风险区域 · 已定位
        </div>
        <div class="absolute bottom-3 left-3 right-3 flex items-center justify-between rounded-lg border border-white/10 bg-black/45 px-2 py-1.5 text-[10px] text-slate-300 backdrop-blur">
          <span>{{ risk?.candidateRegionId || risk?.id || 'candidate-region-01' }}</span>
          <span class="text-cyan-200">空间证据已锁定</span>
        </div>
      </div>

      <div class="min-w-0">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-300">AI SOURCE TRACE</span>
              <StatusBadge v-if="risk" :status="risk.level" size="sm" />
            </div>
            <h2 class="mt-2 text-base font-semibold text-white">{{ risk?.title || workorder.title }}</h2>
            <p class="mt-1 text-xs leading-relaxed text-slate-400">
              {{ task?.name || '智能巡查任务' }} · 风险 {{ workorder.riskId }}
            </p>
          </div>
          <div v-if="profile" class="flex gap-2">
            <div class="rounded-lg border border-cyan-300/15 bg-cyan-300/[0.06] px-3 py-2 text-right">
              <div class="text-[9px] text-slate-400">AI 置信度</div>
              <strong class="text-base text-cyan-200">{{ profile.confidence }}%</strong>
            </div>
            <div class="rounded-lg border border-violet-300/15 bg-violet-300/[0.06] px-3 py-2 text-right">
              <div class="text-[9px] text-slate-400">不确定性</div>
              <strong class="text-base text-violet-200">{{ profile.uncertainty }}%</strong>
            </div>
          </div>
        </div>

        <div class="mt-4 grid gap-2" :class="compact ? 'grid-cols-2' : 'sm:grid-cols-3'">
          <article v-for="item in evidenceItems" :key="item.id" class="rounded-xl border border-white/10 bg-white/[0.035] p-2.5">
            <div class="flex items-center gap-1.5 text-[11px] font-medium text-slate-200">
              <SafeIcon :name="evidenceIcon(item.evidenceType)" :size="13" class="text-cyan-300" />
              {{ item.title }}
            </div>
            <p class="mt-1.5 line-clamp-2 text-[10px] leading-relaxed text-slate-400">{{ item.content }}</p>
          </article>
        </div>

        <div class="mt-3 flex items-start gap-2 rounded-xl border border-cyan-300/10 bg-cyan-300/[0.04] px-3 py-2">
          <SafeIcon name="Sparkles" :size="14" class="mt-0.5 shrink-0 text-cyan-300" />
          <div>
            <div class="text-[10px] font-semibold text-cyan-100">AI 建议处置</div>
            <p class="mt-1 text-[11px] leading-relaxed text-slate-300">
              {{ workorder.aiRecommendation || profile?.recommendation.action || workorder.summary }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

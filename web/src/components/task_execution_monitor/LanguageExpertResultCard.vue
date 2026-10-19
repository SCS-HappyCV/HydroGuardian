<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

const props = defineProps<{ snapshot: AgentPresentationSnapshot }>()

const result = computed(() => props.snapshot.evidence.languageResult)
const statusLabel = computed(() => result.value?.abstained ? '等待人工确认' : result.value?.noTarget ? '未发现目标' : '目标定位完成')
const statusClass = computed(() => result.value?.abstained
  ? 'border-amber-400/20 bg-amber-400/10 text-amber-200'
  : result.value?.noTarget
    ? 'border-sky-400/20 bg-sky-400/10 text-sky-200'
    : 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200')
const verdictLabel = computed(() => ({ passed: '质量校验通过', limited: '结果存在限制', review_required: '建议人工复核', unavailable: '等待质量结果' }[props.snapshot.quality.verdict]))
const noTargetReason = computed(() => result.value?.calibratedNoTarget
  ? '多指标联合校准判定'
  : result.value?.modelNoTarget
    ? '模型直接判定'
    : '未触发无目标判定')

function percent(value?: number) {
  return value === undefined ? '—' : `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`
}

function threshold(value?: number) {
  return value === undefined ? '—' : value.toFixed(2)
}
</script>

<template>
  <section v-if="result" class="overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/[0.08] via-card/60 to-accent/[0.05]">
    <div class="flex flex-col gap-4 border-b border-white/[0.07] p-5 sm:flex-row sm:items-start sm:justify-between">
      <div class="flex items-start gap-3">
        <div class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/15 text-primary"><SafeIcon name="ScanSearch" :size="21" /></div>
        <div>
          <p class="text-[10px] uppercase tracking-[0.18em] text-primary">LANGUAGE-GUIDED EVIDENCE</p>
          <h2 class="mt-1 text-base font-semibold text-foreground">语言专家定位结果</h2>
          <p class="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">{{ result.query || snapshot.task.taskText }}</p>
        </div>
      </div>
      <span class="w-fit rounded-full border px-3 py-1.5 text-[10px] font-medium" :class="statusClass">{{ statusLabel }}</span>
    </div>

    <div class="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-5">
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">任务理解</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ result.taskTypeLabel }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">实际判定阈值</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ threshold(result.appliedThreshold) }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">定位点数</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ result.selectedPoints === undefined ? '—' : result.selectedPoints.toLocaleString('zh-CN') }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">目标点占比</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ percent(result.selectedRatio) }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">执行可信度</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ percent(result.executionConfidence) }}</p></div>
    </div>

    <div class="grid gap-4 px-5 pb-5 lg:grid-cols-[1fr_320px]">
      <div class="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
        <div class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="Network" :size="15" class="text-accent" />结构化任务理解</div>
        <div v-if="result.programSummary.length" class="mt-3 flex flex-wrap gap-2"><span v-for="item in result.programSummary" :key="item" class="rounded-lg border border-accent/15 bg-accent/[0.07] px-2.5 py-1.5 text-[10px] text-accent">{{ item }}</span></div>
        <p v-else class="mt-3 text-[11px] leading-5 text-muted-foreground">专家已完成自然语言编译，详细推理程序可在证据产物流中查看。</p>
      </div>
      <div class="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
        <div class="flex items-center justify-between gap-3"><span class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="ShieldCheck" :size="15" class="text-accent" />结果可信性</span><span class="text-[10px] text-accent">{{ verdictLabel }}</span></div>
        <p class="mt-3 text-[11px] leading-5 text-muted-foreground">{{ result.noTarget ? `${noTargetReason}，空目标掩膜属于有效业务结论，不会生成虚假风险。` : result.abstained ? '专家主动保留结论，建议结合原始点云进行人工确认。' : '已形成可追溯的目标掩膜、概率与推理程序产物。' }}</p>
      </div>
    </div>
  </section>
</template>

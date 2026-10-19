<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

const props = defineProps<{ snapshot: AgentPresentationSnapshot }>()
const result = computed(() => props.snapshot.evidence.semanticResult)
const topClasses = computed(() => result.value?.classes.slice(0, 8) || [])
const distributionConcentrated = computed(() => Boolean(
  result.value?.numPoints && result.value.numPoints >= 10000 && result.value.classes[0]?.pointRatio >= 0.98,
))
const verdictLabel = computed(() => ({ passed: '质量校验通过', limited: '结果存在限制', review_required: '建议人工复核', unavailable: '等待质量结果' }[props.snapshot.quality.verdict]))

function percent(value?: number) {
  return value === undefined ? '—' : `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`
}
</script>

<template>
  <section v-if="result" class="overflow-hidden rounded-2xl border border-cyan-400/20 bg-gradient-to-br from-cyan-400/[0.07] via-card/60 to-primary/[0.05]">
    <div class="flex flex-col gap-4 border-b border-white/[0.07] p-5 sm:flex-row sm:items-start sm:justify-between">
      <div class="flex items-start gap-3">
        <div class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300"><SafeIcon name="Layers3" :size="21" /></div>
        <div><p class="text-[10px] uppercase tracking-[0.18em] text-cyan-300">SCENE SEMANTIC EVIDENCE</p><h2 class="mt-1 text-base font-semibold text-foreground">场景语义理解</h2><p class="mt-1 text-xs leading-5 text-muted-foreground">{{ result.modeLabel }} · 语义结果作为场景证据，不直接等同于风险结论</p></div>
      </div>
      <span class="w-fit rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-[10px] font-medium text-emerald-200">{{ verdictLabel }}</span>
    </div>

    <div class="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4">
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">分析点数</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ result.numPoints === undefined ? '—' : result.numPoints.toLocaleString('zh-CN') }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">识别类别</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ result.numPresentClasses === undefined ? '—' : `${result.numPresentClasses} 类` }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">影像状态</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ result.mode === 'point' ? '本任务未要求影像' : result.imageValidated ? '输入已校验' : '等待校验' }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">实际推理路径</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ result.imageUsed ? '影像与点云联合推理' : '融合训练的点云分支' }}</p></div>
    </div>

    <div class="grid gap-4 px-5 pb-5 lg:grid-cols-[1fr_320px]">
      <div class="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
        <div class="flex items-center justify-between gap-3"><h3 class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="ChartNoAxesColumnIncreasing" :size="15" class="text-cyan-300" />主要地物类别</h3><span class="text-[10px] text-muted-foreground">按点数占比排序</span></div>
        <div v-if="topClasses.length" class="mt-4 space-y-3">
          <div v-for="item in topClasses" :key="item.classId">
            <div class="mb-1.5 flex items-center justify-between gap-3 text-[11px]"><span class="text-card-foreground">{{ item.className }}</span><span class="text-muted-foreground">{{ item.pointCount.toLocaleString('zh-CN') }} 点 · {{ percent(item.pointRatio) }}<template v-if="item.meanConfidence !== undefined"> · 可信度 {{ percent(item.meanConfidence) }}</template></span></div>
            <div class="h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div class="h-full rounded-full bg-gradient-to-r from-cyan-400 to-primary" :style="{ width: `${Math.max(item.pointRatio * 100, 0.6)}%` }" /></div>
          </div>
        </div>
        <p v-else class="mt-3 text-[11px] leading-5 text-muted-foreground">语义产物已经生成，类别摘要等待同步。</p>
        <div v-if="distributionConcentrated" class="mt-4 flex items-start gap-2 rounded-lg border border-amber-400/20 bg-amber-400/[0.07] p-3 text-[10px] leading-4 text-amber-100"><SafeIcon name="TriangleAlert" :size="14" class="mt-0.5 shrink-0" /><span>类别分布高度集中。结构完整性校验已通过，但语义结论建议结合影像或人工样本进一步复核。</span></div>
      </div>

      <div class="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
        <h3 class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="BadgeInfo" :size="15" class="text-cyan-300" />结果说明</h3>
        <p class="mt-3 text-[11px] leading-5 text-muted-foreground">当前结果提供全场景点级语义标签、类别掩膜和概率证据，可与变化检测或空间规则组合形成风险候选。</p>
        <div class="mt-4 flex items-center justify-between rounded-lg border border-white/[0.06] bg-black/10 px-3 py-2 text-[10px]"><span class="text-muted-foreground">可追溯产物</span><span class="font-medium text-cyan-300">{{ result.artifactRefs.length }} 项</span></div>
      </div>
    </div>
  </section>
</template>

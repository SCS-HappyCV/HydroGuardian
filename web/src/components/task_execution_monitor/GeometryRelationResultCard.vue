<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

const props = defineProps<{ snapshot: AgentPresentationSnapshot }>()
const result = computed(() => props.snapshot.evidence.geometryResult)
const bboxSize = computed(() => {
  const min = result.value?.result?.bboxMin
  const max = result.value?.result?.bboxMax
  return min && max ? [max[0] - min[0], max[1] - min[1], max[2] - min[2]] : undefined
})
const outcomeClass = computed(() => result.value?.outcome === 'result' ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200' : 'border-amber-400/20 bg-amber-400/10 text-amber-200')

function percent(value?: number) {
  return value === undefined ? '—' : `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`
}
function meters(value?: number) {
  return value === undefined ? '—' : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} m`
}
function coordinate(value?: [number, number, number]) {
  return value ? value.map((item) => item.toLocaleString('zh-CN', { maximumFractionDigits: 2 })).join('，') : '—'
}
</script>

<template>
  <section v-if="result" class="overflow-hidden rounded-2xl border border-violet-400/20 bg-gradient-to-br from-violet-400/[0.07] via-card/60 to-primary/[0.05]">
    <div class="flex flex-col gap-4 border-b border-white/[0.07] p-5 sm:flex-row sm:items-start sm:justify-between">
      <div class="flex items-start gap-3">
        <div class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-violet-400/10 text-violet-300"><SafeIcon name="Orbit" :size="21" /></div>
        <div><p class="text-[10px] uppercase tracking-[0.18em] text-violet-300">SPATIAL RELATION EVIDENCE</p><h2 class="mt-1 text-base font-semibold text-foreground">空间关系研判</h2><p class="mt-1 text-xs leading-5 text-muted-foreground">{{ result.operationLabel }} · {{ result.targetClassName }}<template v-if="result.referenceClassName"> 相对 {{ result.referenceClassName }}</template></p></div>
      </div>
      <span class="w-fit rounded-full border px-3 py-1.5 text-[10px] font-medium" :class="outcomeClass">{{ result.outcomeLabel }}</span>
    </div>

    <div class="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4">
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">场景总点数</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ result.numPoints === undefined ? '—' : result.numPoints.toLocaleString('zh-CN') }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">关系命中点数</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ result.selectedPoints === undefined ? '—' : result.selectedPoints.toLocaleString('zh-CN') }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">目标命中比例</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ percent(result.selectedTargetRatio) }}</p></div>
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">目标平均高程</p><p class="mt-1.5 text-sm font-semibold text-card-foreground">{{ meters(result.result?.elevationMean) }}</p></div>
    </div>

    <div class="grid gap-4 px-5 pb-5 lg:grid-cols-[1fr_360px]">
      <div class="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
        <h3 class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="Cuboid" :size="15" class="text-violet-300" />目标空间范围</h3>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <div class="rounded-lg border border-white/[0.06] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">中心坐标 X / Y / Z</p><p class="mt-1.5 text-[11px] font-medium text-card-foreground">{{ coordinate(result.result?.centroid) }}</p></div>
          <div class="rounded-lg border border-white/[0.06] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">空间跨度 X / Y / Z</p><p class="mt-1.5 text-[11px] font-medium text-card-foreground">{{ bboxSize ? bboxSize.map((item) => meters(item)).join(' / ') : '—' }}</p></div>
          <div class="rounded-lg border border-white/[0.06] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">最低 / 最高高程</p><p class="mt-1.5 text-[11px] font-medium text-card-foreground">{{ meters(result.result?.elevationMin) }} / {{ meters(result.result?.elevationMax) }}</p></div>
          <div class="rounded-lg border border-white/[0.06] bg-black/10 p-3"><p class="text-[10px] text-muted-foreground">中位高程</p><p class="mt-1.5 text-[11px] font-medium text-card-foreground">{{ meters(result.result?.elevationMedian) }}</p></div>
        </div>
      </div>

      <div class="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
        <h3 class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="Ruler" :size="15" class="text-violet-300" />关系测量</h3>
        <div v-if="result.measurements.length" class="mt-3 space-y-2"><div v-for="item in result.measurements" :key="item.label" class="flex items-center justify-between rounded-lg border border-white/[0.06] bg-black/10 px-3 py-2 text-[10px]"><span class="text-muted-foreground">{{ item.label }}</span><span class="font-medium text-violet-200">{{ item.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }} {{ item.unit }}</span></div></div>
        <p v-else class="mt-3 text-[11px] leading-5 text-muted-foreground">本次为目标范围统计，没有额外的类别间距离或高程关系参数。</p>
        <p class="mt-4 text-[10px] leading-4 text-muted-foreground">几何结果是确定性空间证据；只有与巡查规则匹配后才形成风险候选。</p>
      </div>
    </div>
  </section>
</template>

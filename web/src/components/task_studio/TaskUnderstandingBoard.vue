<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { compileTaskIntent } from '@/lib/task-intent-compiler'

const props = defineProps<{ taskText: string; scenario?: any; zoneName?: string }>()
const intent = computed(() => compileTaskIntent(props.taskText))
const fields = computed(() => [
  ['目标对象', intent.value.target, 'Target'],
  ['空间关系', intent.value.spatialRelations.join(' · '), 'MapPin'],
  ['几何条件', intent.value.geometryConstraints.join(' · ') || '按场景范围筛选', 'Shapes'],
  ['排除条件', intent.value.exclusions.join(' · '), 'CircleOff'],
  ['所需证据', intent.value.evidenceModalities.join(' · '), 'Layers3'],
  ['输出目标', intent.value.ranking, 'ListChecks'],
])
</script>

<template>
  <section class="rounded-2xl border border-white/[0.08] bg-card/55 p-5 shadow-card">
    <div class="flex items-center justify-between gap-3"><div><h2 class="flex items-center gap-2 text-sm font-semibold text-foreground"><SafeIcon name="ScanSearch" :size="17" class="text-accent"/>Agent 任务理解</h2><p class="mt-1 text-[11px] text-muted-foreground">已将自然语言转换为可确认的空间分析条件</p></div><span v-if="taskText" class="rounded-full border border-accent/20 bg-accent/10 px-2.5 py-1 text-[10px] text-accent">理解完成</span></div>
    <div v-if="taskText" class="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3"><div v-for="field in fields" :key="field[0]" class="rounded-xl border border-white/[0.06] bg-black/10 p-3"><p class="flex items-center gap-1.5 text-[10px] text-muted-foreground"><SafeIcon :name="field[2]" :size="12"/>{{ field[0] }}</p><p class="mt-1.5 text-xs leading-5 text-card-foreground">{{ field[1] }}</p></div></div>
    <div v-else class="mt-4 rounded-xl border border-dashed border-white/[0.1] p-5 text-center text-xs text-muted-foreground">输入巡查目标后，Agent 将在这里展示任务理解结果。</div>
  </section>
</template>

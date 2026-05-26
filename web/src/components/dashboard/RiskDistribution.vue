
<script setup lang="ts">
import { VisDonut, VisSingleContainer } from '@unovis/vue'

interface Props {
  high: number
  medium: number
  low: number
  reviewRequired: number
}

const props = defineProps<Props>()

const data = computed(() => [
  { level: '高风险', count: props.high },
  { level: '中风险', count: props.medium },
  { level: '低风险', count: props.low },
  { level: '待复核', count: props.reviewRequired }
])

const colorMap = {
  '高风险': 'hsl(var(--destructive))',
  '中风险': 'hsl(var(--warning))',
  '低风险': 'hsl(var(--success))',
  '待复核': 'hsl(var(--accent))'
}

const colors = computed(() => data.value.map(d => colorMap[d.level as keyof typeof colorMap]))
</script>

<template>
  <div class="surface-base card-padding space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-section-title">风险等级分布</h3>
      <div class="text-sm text-muted-foreground">
        共 {{ high + medium + low + reviewRequired }} 个风险点
      </div>
    </div>

    <VisSingleContainer :data="data" :margin="{ top: 20, bottom: 20, left: 20, right: 20 }">
      <VisDonut :value="(d: any) => d.count" :color="colors" />
    </VisSingleContainer>

    <div class="grid grid-cols-2 gap-3 pt-2">
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded-full" style="background-color: hsl(var(--destructive))" />
        <span class="text-sm text-muted-foreground">高风险: <span class="font-semibold text-foreground">{{ high }}</span></span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded-full" style="background-color: hsl(var(--warning))" />
        <span class="text-sm text-muted-foreground">中风险: <span class="font-semibold text-foreground">{{ medium }}</span></span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded-full" style="background-color: hsl(var(--success))" />
        <span class="text-sm text-muted-foreground">低风险: <span class="font-semibold text-foreground">{{ low }}</span></span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded-full" style="background-color: hsl(var(--accent))" />
        <span class="text-sm text-muted-foreground">待复核: <span class="font-semibold text-foreground">{{ reviewRequired }}</span></span>
      </div>
    </div>
  </div>
</template>

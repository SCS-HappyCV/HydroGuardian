<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Button } from '@/components/ui/button'

defineProps<{
  disabled?: boolean
  isExecuting?: boolean
  progress?: number
  stage?: string
}>()

defineEmits<{ execute: [] }>()
</script>

<template>
  <section class="flex flex-col gap-4 rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/[0.09] to-accent/[0.05] p-5 shadow-[0_16px_50px_hsl(var(--primary)/.08)] sm:flex-row sm:items-center sm:justify-between">
    <div>
      <p class="text-sm font-semibold text-foreground">{{ disabled ? '请先完成巡查任务信息' : '任务信息已准备' }}</p>
      <p class="mt-1 text-xs text-muted-foreground">
        提交后，后台 Agent 将理解目标、生成执行规划并调度专家，真实任务路径会在执行页展示。
      </p>
      <div v-if="isExecuting" class="mt-3 w-full max-w-md">
        <div class="mb-1 flex justify-between text-[10px] text-muted-foreground"><span>{{ stage }}</span><span>{{ Math.round(progress || 0) }}%</span></div>
        <div class="h-1.5 overflow-hidden rounded-full bg-black/20"><div class="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all" :style="{ width: `${progress || 0}%` }" /></div>
      </div>
    </div>
    <Button class="h-11 min-w-[210px] gap-2" :disabled="disabled || isExecuting" @click="$emit('execute')">
      <span v-if="isExecuting" class="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground" />
      <SafeIcon v-else name="Play" :size="17" />
      {{ isExecuting ? '正在提交任务...' : '提交智能巡查' }}
    </Button>
  </section>
</template>

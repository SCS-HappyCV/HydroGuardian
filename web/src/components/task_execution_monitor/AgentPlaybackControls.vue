<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Button } from '@/components/ui/button'

defineProps<{ isRunning: boolean; isPaused: boolean; isTerminal: boolean; progress: number }>()
defineEmits<{ pause: []; resume: []; advance: []; complete: [] }>()
</script>

<template>
  <section class="flex flex-wrap items-center gap-2 rounded-xl border border-white/[0.07] bg-card/35 p-3">
    <span class="mr-2 text-[10px] text-muted-foreground">任务控制</span>
    <Button v-if="isRunning" size="sm" variant="outline" class="h-8 gap-1.5 text-xs" @click="$emit('pause')"><SafeIcon name="Pause" :size="13" />暂停</Button>
    <Button v-else-if="isPaused" size="sm" variant="outline" class="h-8 gap-1.5 text-xs" @click="$emit('resume')"><SafeIcon name="Play" :size="13" />继续</Button>
    <Button v-if="!isTerminal" size="sm" variant="outline" class="h-8 gap-1.5 text-xs" @click="$emit('advance')"><SafeIcon name="SkipForward" :size="13" />下一步</Button>
    <Button v-if="!isTerminal" size="sm" class="h-8 gap-1.5 text-xs" @click="$emit('complete')"><SafeIcon name="FastForward" :size="13" />完成分析</Button>
    <span class="ml-auto text-[10px] text-muted-foreground">{{ progress }}%</span>
  </section>
</template>

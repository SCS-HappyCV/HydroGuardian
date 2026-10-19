<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'

defineProps<{ completeness: number; status: string; sceneName: string }>()
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/[0.08] bg-card/50 px-5 py-4">
    <div class="flex items-center gap-3">
      <span class="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><SafeIcon name="Orbit" :size="20" /></span>
      <div><h1 class="text-lg font-semibold text-foreground">Agent 任务指挥台</h1><p class="mt-0.5 text-xs text-muted-foreground">用自然语言下达巡查要求，由 Agent 组织水利遥感专家能力</p></div>
    </div>
    <div class="flex items-center gap-3 text-xs">
      <span class="text-muted-foreground">{{ sceneName }}</span>
      <span class="flex items-center gap-1.5 rounded-full border border-accent/20 bg-accent/10 px-2.5 py-1 text-accent"><i class="h-1.5 w-1.5 rounded-full bg-accent" />{{ status }}</span>
      <span class="rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-muted-foreground">数据 {{ completeness }}/4 就绪</span>
    </div>
  </div>
</template>

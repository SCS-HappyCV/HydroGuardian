<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

defineProps<{ snapshot?: AgentPresentationSnapshot | null }>()
</script>

<template>
  <section v-if="snapshot" class="rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/[0.08] to-accent/[0.04] p-5">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"><div><p class="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-primary"><SafeIcon name="Sparkles" :size="13" />Agent Decision</p><h2 class="mt-2 text-lg font-semibold text-foreground">{{ snapshot.decision.title }}</h2><p class="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">{{ snapshot.decision.summary }}</p></div><div class="grid grid-cols-2 gap-2 text-center text-[10px]"><div class="rounded-xl border border-white/[0.08] bg-black/10 px-4 py-3"><strong class="block text-base text-card-foreground">{{ snapshot.decision.selectedTools.length }}</strong><span class="text-muted-foreground">调用能力</span></div><div class="rounded-xl border border-white/[0.08] bg-black/10 px-4 py-3"><strong class="block text-base text-accent">{{ snapshot.evidence.artifacts.length }}</strong><span class="text-muted-foreground">证据产物</span></div></div></div>
    <div class="mt-4 flex flex-wrap gap-2"><span v-for="tool in snapshot.decision.selectedTools" :key="tool" class="rounded-lg border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5 text-[10px] text-card-foreground">{{ snapshot.capabilities.find((item) => item.capabilityId === tool)?.name || tool }}</span><span v-if="snapshot.decision.reviewRequired" class="rounded-lg border border-amber-400/20 bg-amber-400/10 px-2.5 py-1.5 text-[10px] text-amber-200">结果可能需要人工复核</span></div>
  </section>
</template>

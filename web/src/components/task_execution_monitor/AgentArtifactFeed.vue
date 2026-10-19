<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

defineProps<{ snapshot?: AgentPresentationSnapshot | null; downloadable?: boolean }>()
defineEmits<{ download: [artifactId: string] }>()
</script>

<template>
  <section class="rounded-2xl border border-white/[0.08] bg-card/55 p-5 shadow-card">
    <div class="mb-4 flex items-center justify-between"><div><h2 class="flex items-center gap-2 text-sm font-semibold text-foreground"><SafeIcon name="PackageCheck" :size="17" class="text-accent" />证据产物流</h2><p class="mt-1 text-[11px] text-muted-foreground">专家产物随执行过程逐步汇聚</p></div><span class="text-[10px] text-accent">{{ snapshot?.evidence.artifacts.length || 0 }} 项已生成</span></div>
    <div v-if="snapshot?.evidence.artifacts.length" class="space-y-2.5"><article v-for="artifact in snapshot.evidence.artifacts" :key="artifact.artifactId" class="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3"><div class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent"><SafeIcon :name="artifact.mediaType.includes('image') ? 'Image' : 'FileJson'" :size="16" /></div><div class="min-w-0 flex-1"><p class="truncate text-xs font-medium text-card-foreground">{{ artifact.title }}</p><p class="mt-1 truncate text-[10px] text-muted-foreground">{{ artifact.role }} · 第 {{ artifact.availableAtStep }} 步生成</p></div><button v-if="downloadable" type="button" class="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-primary/10 hover:text-primary" title="下载产物" @click="$emit('download', artifact.artifactId)"><SafeIcon name="Download" :size="15" /></button><SafeIcon v-else name="CheckCircle2" :size="15" class="text-accent" /></article></div>
    <div v-else class="rounded-xl border border-dashed border-white/[0.09] p-6 text-center text-xs text-muted-foreground">尚未生成证据产物</div>
  </section>
</template>

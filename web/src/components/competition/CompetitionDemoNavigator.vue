<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { competitionDemoStages, getCompetitionDemoSession, resolveCompetitionDemoStage, updateCompetitionDemoStage } from '@/lib/competition-demo-session'
import { resetCompetitionDemoState } from '@/lib/competition-demo-reset'
import { startCompetitionDemoSession } from '@/lib/competition-demo-session'
import * as WorkorderService from '@/data/WorkorderService'

const props = defineProps<{ currentPath: string }>()
const active = ref(false)
const currentStage = computed(() => resolveCompetitionDemoStage(props.currentPath))
const currentIndex = computed(() => competitionDemoStages.findIndex((item) => item.id === currentStage.value))
const nextStage = computed(() => competitionDemoStages[Math.min(currentIndex.value + 1, competitionDemoStages.length - 1)])

function navigate(href: string, stage: typeof competitionDemoStages[number]['id']) {
  updateCompetitionDemoStage(stage)
  window.location.href = resolveHref(href, stage)
}

function resolveHref(href: string, stage: typeof competitionDemoStages[number]['id']) {
  if (stage !== 'workorder' && stage !== 'review') return href
  const order = WorkorderService.getAll().find((item) => item.riskId === 'risk-agent-001') || WorkorderService.getAll()[0]
  if (!order) return stage === 'review' ? './workorder-center.html?status=review' : './workorder-center.html'
  return stage === 'review' ? `./workorder-review.html?orderId=${order.id}` : `./workorder-detail.html?orderId=${order.id}`
}

function resetDemo() {
  resetCompetitionDemoState()
  startCompetitionDemoSession()
  toast.success('典型案例已重置')
  window.setTimeout(() => window.location.href = competitionDemoStages[0].href, 350)
}

onMounted(() => {
  active.value = Boolean(getCompetitionDemoSession()?.active)
  if (active.value && currentStage.value) updateCompetitionDemoStage(currentStage.value)
})
</script>

<template>
  <section v-if="active && currentStage" class="border-b border-cyan-300/15 bg-[#081827] px-4 py-2 text-white"><div class="mx-auto flex max-w-[1600px] items-center gap-3"><div class="hidden min-w-[132px] items-center gap-2 text-[10px] font-semibold text-cyan-200 xl:flex"><SafeIcon name="Route" :size="14" />业务闭环流程</div><div class="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"><button v-for="(stage, index) in competitionDemoStages" :key="stage.id" class="flex min-w-fit items-center gap-2 rounded-lg px-2.5 py-1.5 text-left transition" :class="stage.id === currentStage ? 'bg-cyan-300/12 text-cyan-100' : index < currentIndex ? 'text-emerald-300' : 'text-slate-500 hover:bg-white/5'" @click="navigate(stage.href, stage.id)"><span class="grid h-6 w-6 place-items-center rounded-md" :class="stage.id === currentStage ? 'bg-cyan-300 text-[#07111f]' : 'bg-white/[0.05]' "><SafeIcon :name="index < currentIndex ? 'Check' : stage.icon" :size="12" /></span><strong class="text-[10px] font-medium">{{ stage.label }}</strong></button></div><div class="hidden max-w-[190px] border-l border-white/10 pl-3 2xl:block"><p class="text-[9px] text-slate-500">当前环节</p><p class="mt-0.5 truncate text-[10px] text-cyan-100">{{ competitionDemoStages[currentIndex]?.value }}</p></div><button class="hidden items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-[10px] text-slate-300 hover:bg-white/5 lg:flex" @click="resetDemo"><SafeIcon name="RotateCcw" :size="12" />重新载入</button><button v-if="currentIndex < competitionDemoStages.length - 1" class="flex shrink-0 items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-[10px] font-medium" @click="navigate(nextStage.href, nextStage.id)">下一环节<SafeIcon name="ArrowRight" :size="12" /></button></div></section>
</template>

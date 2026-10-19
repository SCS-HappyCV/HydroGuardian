<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentWorkflowStepView, AgentWorkflowView } from '@/lib/agent-presentation-types'

const props = defineProps<{ workflow?: AgentWorkflowView | null }>()

const statusMeta = {
  pending: { label: '等待调度', icon: 'CircleDashed', tone: 'text-slate-400', dot: 'bg-slate-500', glow: 'from-slate-500/40' },
  running: { label: '正在执行', icon: 'Loader2', tone: 'text-cyan-300', dot: 'bg-cyan-300', glow: 'from-cyan-400/70' },
  completed: { label: '执行完成', icon: 'Check', tone: 'text-emerald-300', dot: 'bg-emerald-300', glow: 'from-emerald-400/65' },
  skipped: { label: '已跳过', icon: 'SkipForward', tone: 'text-amber-300', dot: 'bg-amber-300', glow: 'from-amber-400/60' },
  failed: { label: '执行异常', icon: 'X', tone: 'text-rose-300', dot: 'bg-rose-300', glow: 'from-rose-400/70' },
} as const

const originMeta = {
  planner: { label: '智能规划', icon: 'Sparkles', tone: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200' },
  planned: { label: '规划步骤', icon: 'Route', tone: 'border-blue-400/25 bg-blue-400/10 text-blue-200' },
  runtime: { label: '运行时增强', icon: 'Workflow', tone: 'border-violet-400/25 bg-violet-400/10 text-violet-200' },
  verification: { label: '质量门禁', icon: 'ShieldCheck', tone: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200' },
} as const

function stepOrigin(step: AgentWorkflowStepView, index: number) {
  return step.origin || (index === 0 ? 'planner' : 'planned')
}

function dependencyNames(step: AgentWorkflowStepView) {
  return step.dependsOn.map((id) => props.workflow?.steps.find((item) => item.stepId === id)?.title || id)
}

</script>

<template>
  <section class="relative overflow-hidden rounded-3xl border border-white/[0.09] bg-[#07121d]/95 shadow-[0_26px_80px_rgba(0,0,0,0.3)]">
    <div class="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_18%_0%,rgba(34,211,238,0.12),transparent_42%),radial-gradient(circle_at_82%_0%,rgba(139,92,246,0.1),transparent_38%)]" />
    <header class="relative border-b border-white/[0.07] px-5 py-4 sm:px-6">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div class="flex items-center gap-2.5">
            <span class="grid h-9 w-9 place-items-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-300 shadow-[0_0_24px_rgba(34,211,238,0.08)]"><SafeIcon name="GitBranch" :size="18" /></span>
            <div><h2 class="text-base font-semibold tracking-wide text-white">动态专家协作路径</h2><p class="mt-0.5 text-[11px] text-slate-400">后端规划与实际执行路径实时对齐</p></div>
          </div>
          <p v-if="workflow" class="mt-2 max-w-2xl text-xs leading-5 text-slate-400">{{ workflow.summary }}</p>
        </div>
        <span v-if="workflow" class="w-fit rounded-full border border-cyan-400/20 bg-cyan-400/[0.07] px-3 py-1.5 text-[10px] text-cyan-200">后台实时路径</span>
      </div>
    </header>

    <div v-if="workflow" class="relative p-4 sm:p-6">
      <div class="grid gap-3 sm:grid-cols-2">
        <article
          v-for="(step, index) in workflow.steps"
          :key="step.stepId"
          class="group relative min-h-[206px] overflow-hidden rounded-2xl border border-white/[0.075] bg-gradient-to-b from-white/[0.045] to-white/[0.018] p-4 transition duration-300 hover:-translate-y-0.5 hover:border-white/[0.14] hover:bg-white/[0.055]"
        >
          <div class="absolute inset-x-0 top-0 h-px bg-gradient-to-r to-transparent" :class="statusMeta[step.status].glow" />
          <div v-if="step.status === 'running'" class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(34,211,238,0.09),transparent_52%)]" />

          <div class="relative flex items-start justify-between gap-3">
            <div class="flex min-w-0 items-center gap-2.5">
              <span class="grid h-10 w-10 place-items-center rounded-xl border border-white/[0.08] bg-black/20" :class="statusMeta[step.status].tone">
                <SafeIcon :name="step.status === 'running' ? 'Loader2' : statusMeta[step.status].icon" :size="18" :class="step.status === 'running' && 'animate-spin'" />
              </span>
              <div>
                <p class="font-mono text-[9px] tracking-[0.18em] text-slate-600">STAGE {{ String(index + 1).padStart(2, '0') }}</p>
                <p class="mt-1 flex whitespace-nowrap items-center gap-1.5 text-[10px]" :class="statusMeta[step.status].tone"><span class="h-1.5 w-1.5 rounded-full" :class="statusMeta[step.status].dot" />{{ statusMeta[step.status].label }}</p>
              </div>
            </div>
            <span class="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-1 text-[9px]" :class="originMeta[stepOrigin(step, index)].tone"><SafeIcon :name="originMeta[stepOrigin(step, index)].icon" :size="11" />{{ originMeta[stepOrigin(step, index)].label }}</span>
          </div>

          <div class="relative mt-4">
            <h3 class="text-sm font-semibold text-slate-100">{{ step.title }}</h3>
            <p class="mt-1 text-[10px] tracking-wide text-cyan-300/75">{{ step.capabilityName }}</p>
            <p class="mt-2 line-clamp-2 min-h-[40px] text-xs leading-5 text-slate-400">{{ step.summary }}</p>
          </div>

          <div class="relative mt-4 space-y-2 border-t border-white/[0.06] pt-3 text-[10px]">
            <div v-if="dependencyNames(step).length" class="flex items-start gap-2 text-slate-500"><SafeIcon name="CornerDownRight" :size="12" class="mt-0.5 shrink-0 text-slate-600" /><span>承接：{{ dependencyNames(step).join('、') }}</span></div>
            <div v-if="step.executor" class="flex items-center gap-2 text-slate-500"><SafeIcon name="Cpu" :size="12" class="text-slate-600" /><span class="truncate">执行节点：{{ step.executor }}</span></div>
            <div class="flex items-center justify-between gap-3 pt-1">
              <span class="inline-flex items-center gap-1.5 text-slate-500"><SafeIcon name="PackageCheck" :size="12" />{{ step.artifactRefs.length ? `${step.artifactRefs.length} 项产物` : '等待产物' }}</span>
              <span v-if="step.verificationPolicy === 'required'" class="inline-flex items-center gap-1 text-emerald-300/80"><SafeIcon name="ShieldCheck" :size="12" />要求质量核验</span>
              <span v-else-if="step.durationMs" class="font-mono text-slate-500">{{ step.durationMs }}ms</span>
            </div>
          </div>

          <div v-if="step.status === 'running'" class="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-cyan-400/10"><span class="block h-full w-1/2 animate-[stage-run_1.4s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-cyan-300 to-transparent" /></div>
        </article>
      </div>
    </div>
    <div v-else class="relative grid min-h-52 place-items-center p-8 text-center"><div><span class="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-white/10 bg-white/[0.04] text-slate-500"><SafeIcon name="Route" :size="21" /></span><p class="mt-3 text-xs text-slate-500">等待规划智能体生成动态协作路径</p></div></div>
  </section>
</template>

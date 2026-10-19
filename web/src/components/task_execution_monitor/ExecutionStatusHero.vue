<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentExecutionStatus, AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

const props = defineProps<{ snapshot: AgentPresentationSnapshot; taskName: string; providerMode: 'local' | 'remote' }>()

const expertSteps = computed(() => props.snapshot.workflow?.steps.filter((step) => step.origin !== 'planner') || [])
const plannerStep = computed(() => props.snapshot.workflow?.steps.find((step) => step.origin === 'planner'))
const completedExperts = computed(() => expertSteps.value.filter((step) => step.status === 'completed').length)
const progress = computed(() => props.snapshot.workflow?.progress ?? (props.snapshot.status === 'completed' ? 100 : 0))

const statusMeta: Record<AgentExecutionStatus, { label: string; summary: string; icon: string; tone: string; pulse?: boolean }> = {
  idle: { label: '任务已提交', summary: '等待规划服务接收任务', icon: 'Clock3', tone: 'text-slate-300 border-slate-400/20 bg-slate-400/10' },
  preparing: { label: '正在生成执行规划', summary: 'Agent 正在理解目标、核对数据并选择专家能力', icon: 'Sparkles', tone: 'text-cyan-200 border-cyan-400/25 bg-cyan-400/10', pulse: true },
  running: { label: '专家协同执行中', summary: '后端正在按动态规划调度专家并汇聚结果', icon: 'Activity', tone: 'text-blue-200 border-blue-400/25 bg-blue-400/10', pulse: true },
  paused: { label: '执行已暂停', summary: '当前任务保留执行上下文，等待继续', icon: 'Pause', tone: 'text-amber-200 border-amber-400/25 bg-amber-400/10' },
  completed: { label: '智能巡查已完成', summary: '规划、专家分析和结果归档均已完成', icon: 'BadgeCheck', tone: 'text-emerald-200 border-emerald-400/25 bg-emerald-400/10' },
  review_required: { label: '分析完成，建议复核', summary: '结果已生成，部分证据需要人工确认', icon: 'ShieldAlert', tone: 'text-amber-200 border-amber-400/25 bg-amber-400/10' },
  clarification_required: { label: '需要补充任务信息', summary: 'Planner 无法安全生成执行路径，请补充必要输入', icon: 'MessageSquareMore', tone: 'text-amber-200 border-amber-400/25 bg-amber-400/10' },
  abstained: { label: '已保留自动结论', summary: '现有证据不足，Agent 未强行生成判断', icon: 'ShieldCheck', tone: 'text-amber-200 border-amber-400/25 bg-amber-400/10' },
  blocked: { label: '等待专家能力恢复', summary: '规划已经保留，所需专家当前不可用', icon: 'ServerOff', tone: 'text-rose-200 border-rose-400/25 bg-rose-400/10' },
  cancelled: { label: '任务已取消', summary: '执行已安全停止，已生成的产物仍然保留', icon: 'CircleStop', tone: 'text-slate-300 border-slate-400/20 bg-slate-400/10' },
  failed: { label: '任务执行异常', summary: '执行过程出现错误，可查看详情后重新执行', icon: 'TriangleAlert', tone: 'text-rose-200 border-rose-400/25 bg-rose-400/10' },
}

const current = computed(() => statusMeta[props.snapshot.status])
const connectionLabel = computed(() => props.providerMode === 'remote'
  ? props.snapshot.status === 'running' ? '专家服务在线' : '已连接智能分析服务'
  : '预置分析环境')
</script>

<template>
  <section class="relative overflow-hidden rounded-3xl border border-white/[0.09] bg-[#07131f] p-5 shadow-[0_28px_90px_rgba(0,0,0,.28)] sm:p-6">
    <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_0%,rgba(34,211,238,.14),transparent_38%),radial-gradient(circle_at_88%_10%,rgba(59,130,246,.12),transparent_36%)]" />
    <div class="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
      <div class="min-w-0">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px]" :class="current.tone"><i class="h-1.5 w-1.5 rounded-full bg-current" :class="current.pulse && 'animate-pulse'" />{{ current.label }}</span>
          <span class="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] text-slate-400">{{ connectionLabel }}</span>
        </div>
        <h1 class="truncate text-xl font-semibold text-white sm:text-2xl">{{ taskName }}</h1>
        <p class="mt-2 flex items-center gap-2 text-xs leading-5 text-slate-400"><SafeIcon :name="current.icon" :size="15" :class="current.tone.split(' ')[0]" />{{ current.summary }}</p>
      </div>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:min-w-[520px]">
        <div class="rounded-2xl border border-white/[0.07] bg-black/15 p-3"><p class="text-[9px] tracking-wider text-slate-500">总体进度</p><strong class="mt-1 block text-lg text-cyan-200">{{ progress }}%</strong></div>
        <div class="rounded-2xl border border-white/[0.07] bg-black/15 p-3"><p class="text-[9px] tracking-wider text-slate-500">任务规划</p><strong class="mt-1 block text-sm text-white">{{ plannerStep?.status === 'completed' ? '已完成' : plannerStep?.status === 'running' ? '进行中' : '等待中' }}</strong></div>
        <div class="rounded-2xl border border-white/[0.07] bg-black/15 p-3"><p class="text-[9px] tracking-wider text-slate-500">专家步骤</p><strong class="mt-1 block text-lg text-white">{{ completedExperts }}<small class="text-xs text-slate-500"> / {{ expertSteps.length }}</small></strong></div>
        <div class="rounded-2xl border border-white/[0.07] bg-black/15 p-3"><p class="text-[9px] tracking-wider text-slate-500">证据产物</p><strong class="mt-1 block text-lg text-emerald-200">{{ snapshot.evidence.artifacts.length }}</strong></div>
      </div>
    </div>
    <div class="relative mt-5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div class="h-full rounded-full bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 transition-all duration-700" :style="{ width: `${progress}%` }" /></div>
  </section>
</template>

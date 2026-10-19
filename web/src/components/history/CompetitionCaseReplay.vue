<script setup lang="ts">
import { computed } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ClosureTimeline from '@/components/workorder_detail/ClosureTimeline.vue'
import { competitionDemo } from '@/data/CompetitionDemoData'
import * as TaskService from '@/data/TaskService'
import * as TaskResultService from '@/data/TaskResultService'
import * as RiskEventService from '@/data/RiskEventService'
import * as WorkorderService from '@/data/WorkorderService'
import * as WorkorderTimelineService from '@/data/WorkorderTimelineService'
import * as WorkorderEvidenceService from '@/data/WorkorderEvidenceService'
import * as WorkorderReviewService from '@/data/WorkorderReviewService'
import * as ZoneService from '@/data/ZoneService'
import { compileTaskIntent } from '@/lib/task-intent-compiler'
import { getAgentDemoScenario } from '@/data/agent-demo/scenarios'
import { localAgentRuntime } from '@/lib/local-agent-runtime'
import { buildRiskEvidenceProfile } from '@/lib/risk-evidence'
import { resetCompetitionDemoState } from '@/lib/competition-demo-reset'

const task = TaskService.getById(competitionDemo.taskId)!
const taskResult = TaskResultService.getByTaskIdVO(competitionDemo.taskId)
const risks = RiskEventService.query({ filter: { taskId: competitionDemo.taskId } })
const primaryRisk = RiskEventService.getById(competitionDemo.primaryRiskId)!
const workorder = WorkorderService.getById(competitionDemo.workorderId)!
const timeline = WorkorderTimelineService.queryByOrderId(competitionDemo.workorderId)
const evidence = WorkorderEvidenceService.query({ filter: { orderId: competitionDemo.workorderId } })
const review = WorkorderReviewService.getByOrderIdVO(competitionDemo.workorderId)
const zone = ZoneService.getById(task.zoneId)
const intent = compileTaskIntent(task.inputText)
const agentSnapshot = localAgentRuntime.getSnapshot(competitionDemo.taskId)
  || getAgentDemoScenario('near-water-disturbance-workflow')?.timeline.at(-1)?.snapshot
const agentStages = agentSnapshot?.workflow?.steps || []
const riskProfile = buildRiskEvidenceProfile(primaryRisk)

const durationSeconds = computed(() => {
  if (!task.startedAt || !task.finishedAt) return 0
  return Math.round((new Date(task.finishedAt).getTime() - new Date(task.startedAt).getTime()) / 1000)
})

const closureMinutes = computed(() => {
  return Math.round((new Date(workorder.updatedAt).getTime() - new Date(workorder.createdAt).getTime()) / 60000)
})

const journey = [
  { index: '01', title: '巡查目标', detail: '自然语言描述任务', icon: 'MessageSquareText', href: `./task-studio.html?taskId=${task.id}&sceneId=${competitionDemo.sceneId}` },
  { index: '02', title: '智能执行', detail: '动态多专家协作', icon: 'Network', href: `./task-execution-monitor.html?taskId=${task.id}` },
  { index: '03', title: '风险研判', detail: '四模态证据交叉验证', icon: 'ScanSearch', href: `./risk-workspace.html?taskId=${task.id}&riskId=${primaryRisk.id}&caseId=${competitionDemo.caseId}` },
  { index: '04', title: '现场处置', detail: 'AI 建议进入工单', icon: 'HardHat', href: `./workorder-detail.html?orderId=${workorder.id}` },
  { index: '05', title: '复核闭环', detail: '证据完整并关闭', icon: 'BadgeCheck', href: `./workorder-detail.html?orderId=${workorder.id}` },
]

const outcomeMetrics = [
  { label: 'AI 执行耗时', value: `${Math.floor(durationSeconds.value / 60)}m ${durationSeconds.value % 60}s`, note: '多智能体自动完成', icon: 'Timer', tone: 'text-cyan-300' },
  { label: '识别候选风险', value: `${risks.length} 处`, note: '1 高风险 · 1 待复核', icon: 'ShieldAlert', tone: 'text-[#ff837c]' },
  { label: '闭环处置时长', value: `${Math.floor(closureMinutes.value / 60)}h ${closureMinutes.value % 60}m`, note: '从发现到复核关闭', icon: 'Route', tone: 'text-violet-300' },
  { label: '证据可追溯率', value: '100%', note: '任务、风险、工单全关联', icon: 'Link2', tone: 'text-emerald-300' },
]

const evidenceCards = computed(() => riskProfile.evidence.map((item) => ({
  ...item,
  metric: item.id === 'image'
    ? '0.2m 正射分辨率'
    : item.id === 'geometry'
      ? '局部高差 1.8m'
      : item.id === 'change'
        ? '变化置信度 0.91'
        : '距水线 18m',
})))

function navigate(href: string) {
  window.location.href = href
}

function resetGoldenCase() {
  resetCompetitionDemoState()
  toast.success('典型案例数据已恢复')
  window.setTimeout(() => window.location.reload(), 450)
}

function restartGoldenCase() {
  resetCompetitionDemoState()
  navigate(`./task-studio.html?taskId=${competitionDemo.taskId}&sceneId=${competitionDemo.sceneId}`)
}
</script>

<template>
  <div class="min-h-full bg-[#07111f] text-white">
    <section class="relative overflow-hidden border-b border-white/10 px-5 py-7 lg:px-8">
      <div class="absolute inset-0 opacity-40 [background-image:radial-gradient(circle_at_18%_22%,rgba(47,128,237,.28),transparent_32%),radial-gradient(circle_at_82%_15%,rgba(45,212,191,.17),transparent_28%)]" />
      <div class="relative mx-auto max-w-[1500px]">
        <div class="flex flex-col justify-between gap-6 xl:flex-row xl:items-end">
          <div class="max-w-4xl">
            <div class="flex flex-wrap items-center gap-2">
              <span class="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-[10px] font-semibold tracking-[0.18em] text-cyan-200">
                典型业务案例 · {{ competitionDemo.caseId }}
              </span>
              <span class="flex items-center gap-1.5 rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-[10px] font-medium text-emerald-300">
                <SafeIcon name="BadgeCheck" :size="12" />
                已完成闭环
              </span>
            </div>
            <h1 class="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">近水扰动与疑似沟渠智能巡查案例</h1>
            <p class="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
              从一句自然语言巡查目标出发，HydroGuardian 自动完成空间程序编译、多模态证据检索、风险研判、处置建议和现场闭环。
            </p>
            <div class="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-400">
              <span class="flex items-center gap-1.5"><SafeIcon name="MapPinned" :size="14" class="text-cyan-300" />{{ zone?.name }}</span>
              <span class="flex items-center gap-1.5"><SafeIcon name="CalendarClock" :size="14" class="text-cyan-300" />2026-05-24</span>
              <span class="flex items-center gap-1.5"><SafeIcon name="Layers3" :size="14" class="text-cyan-300" />正射影像 · 点云 · 前后时相</span>
            </div>
          </div>

          <div class="flex flex-wrap gap-2">
            <Button variant="outline" class="gap-2 border-white/15 bg-white/[0.03]" @click="resetGoldenCase">
              <SafeIcon name="RotateCcw" :size="15" />
              重置案例数据
            </Button>
            <Button class="gap-2 shadow-[0_0_24px_rgba(47,128,237,.24)]" @click="restartGoldenCase">
              <SafeIcon name="Play" :size="15" />
              重新执行流程
            </Button>
          </div>
        </div>

        <div class="mt-7 grid grid-cols-2 gap-2 lg:grid-cols-5">
          <button
            v-for="item in journey"
            :key="item.index"
            type="button"
            class="group relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.035] p-3 text-left transition hover:border-cyan-300/30 hover:bg-cyan-300/[0.05]"
            @click="navigate(item.href)"
          >
            <div class="flex items-start justify-between">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-300/10 text-cyan-300">
                <SafeIcon :name="item.icon" :size="16" />
              </span>
              <span class="font-mono text-[10px] text-slate-600">{{ item.index }}</span>
            </div>
            <div class="mt-3 text-xs font-semibold text-slate-100">{{ item.title }}</div>
            <div class="mt-1 text-[10px] text-slate-500">{{ item.detail }}</div>
            <span class="absolute bottom-0 left-0 h-px w-full bg-gradient-to-r from-cyan-300/70 to-transparent" />
          </button>
        </div>
      </div>
    </section>

    <main class="mx-auto max-w-[1500px] space-y-5 px-5 py-6 lg:px-8">
      <section class="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <article v-for="metric in outcomeMetrics" :key="metric.label" class="rounded-2xl border border-white/10 bg-[#0a1726] p-4">
          <div class="flex items-center justify-between">
            <span class="text-[10px] text-slate-500">{{ metric.label }}</span>
            <SafeIcon :name="metric.icon" :size="16" :class="metric.tone" />
          </div>
          <div class="mt-2 text-xl font-semibold text-white">{{ metric.value }}</div>
          <div class="mt-1 text-[10px] text-slate-500">{{ metric.note }}</div>
        </article>
      </section>

      <section class="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <article class="rounded-2xl border border-white/10 bg-[#0a1726] p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 class="flex items-center gap-2 text-sm font-semibold">
                <SafeIcon name="MessageSquareText" :size="17" class="text-cyan-300" />
                从自然语言到可执行巡查
              </h2>
              <p class="mt-1 text-[10px] text-slate-500">AI 意图编译结果已固化到案例记录</p>
            </div>
            <span class="rounded-full bg-cyan-300/10 px-2 py-1 text-[10px] text-cyan-300">任务编译成功</span>
          </div>
          <blockquote class="mt-4 rounded-xl border border-cyan-300/15 bg-cyan-300/[0.045] p-4 text-sm leading-7 text-slate-200">
            “{{ task.inputText }}”
          </blockquote>
          <div class="mt-4 grid grid-cols-2 gap-2">
            <div class="rounded-xl border border-white/10 bg-white/[0.025] p-3">
              <div class="text-[10px] text-slate-500">识别目标</div>
              <div class="mt-1 text-xs text-white">{{ intent.target }}</div>
            </div>
            <div class="rounded-xl border border-white/10 bg-white/[0.025] p-3">
              <div class="text-[10px] text-slate-500">证据模态</div>
              <div class="mt-1 text-xs text-white">{{ intent.evidenceModalities.join(' · ') }}</div>
            </div>
            <div class="rounded-xl border border-white/10 bg-white/[0.025] p-3">
              <div class="text-[10px] text-slate-500">空间关系</div>
              <div class="mt-1 text-xs text-white">{{ intent.spatialRelations.join('；') }}</div>
            </div>
            <div class="rounded-xl border border-white/10 bg-white/[0.025] p-3">
              <div class="text-[10px] text-slate-500">安全策略</div>
              <div class="mt-1 text-xs text-white">{{ intent.reviewPolicy }}</div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-white/10 bg-[#0a1726] p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 class="flex items-center gap-2 text-sm font-semibold">
                <SafeIcon name="Network" :size="17" class="text-violet-300" />
                动态多专家协作
              </h2>
              <p class="mt-1 text-[10px] text-slate-500">任务、证据、风险与闭环智能体共同完成</p>
            </div>
            <span class="text-[10px] text-emerald-300">{{ agentStages.length }}/{{ agentStages.length }} 已完成</span>
          </div>
          <div class="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <div v-for="stage in agentStages" :key="stage.stepId" class="rounded-xl border border-emerald-300/10 bg-emerald-300/[0.035] p-3">
              <div class="flex items-center justify-between">
                <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-300/10 text-emerald-300">
                  <SafeIcon name="Workflow" :size="14" />
                </span>
                <SafeIcon name="CheckCircle2" :size="13" class="text-emerald-300" />
              </div>
              <div class="mt-2 text-[11px] font-medium text-slate-200">{{ stage.title }}</div>
              <div class="mt-1 truncate text-[9px] text-slate-500">{{ stage.capabilityName }}</div>
            </div>
          </div>
        </article>
      </section>

      <section class="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <article class="overflow-hidden rounded-2xl border border-white/10 bg-[#0a1726]">
          <header class="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div>
              <h2 class="flex items-center gap-2 text-sm font-semibold">
                <SafeIcon name="ScanSearch" :size="17" class="text-cyan-300" />
                多模态风险证据
              </h2>
              <p class="mt-1 text-[10px] text-slate-500">{{ taskResult?.summary }}</p>
            </div>
            <StatusBadge :status="primaryRisk.level" size="sm" />
          </header>
          <div class="grid min-h-[320px] md:grid-cols-[1.05fr_0.95fr]">
            <div class="relative overflow-hidden bg-[linear-gradient(150deg,#173c3d_0%,#286e75_33%,#ae8c5f_34%,#43593b_60%,#172d29_100%)]">
              <svg class="absolute inset-0 h-full w-full" viewBox="0 0 600 380" preserveAspectRatio="none">
                <path d="M-40 58 C120 10 182 135 302 113 C422 92 470 18 640 56 L640 171 C470 133 407 224 282 207 C147 190 86 118 -40 186Z" fill="#287f94" fill-opacity=".9" />
                <path d="M277 230 C335 190 447 214 483 267 C505 300 453 332 384 330 C319 328 256 286 277 230Z" fill="#ff5d5d" fill-opacity=".18" stroke="#ff837c" stroke-width="4" stroke-dasharray="9 6" />
                <path d="M310 244 C352 222 421 236 454 269" fill="none" stroke="#ffd06b" stroke-width="7" />
              </svg>
              <div class="absolute left-4 top-4 rounded-lg border border-white/10 bg-black/45 px-3 py-2 text-[10px] text-cyan-100 backdrop-blur">正射影像 · 风险轮廓</div>
              <div class="absolute bottom-4 left-4 right-4 grid grid-cols-3 gap-2">
                <div class="rounded-lg bg-black/50 p-2 backdrop-blur"><div class="text-[9px] text-slate-500">风险分</div><strong class="text-sm text-[#ff837c]">{{ primaryRisk.score }}</strong></div>
                <div class="rounded-lg bg-black/50 p-2 backdrop-blur"><div class="text-[9px] text-slate-500">距水线</div><strong class="text-sm text-cyan-200">18m</strong></div>
                <div class="rounded-lg bg-black/50 p-2 backdrop-blur"><div class="text-[9px] text-slate-500">变化置信度</div><strong class="text-sm text-violet-200">91%</strong></div>
              </div>
            </div>
            <div class="grid content-center gap-2 p-4">
              <article v-for="item in evidenceCards" :key="item.id" class="rounded-xl border border-white/10 bg-white/[0.025] p-3">
                <div class="flex items-center justify-between gap-2">
                  <span class="flex items-center gap-1.5 text-[11px] font-medium text-slate-200">
                    <SafeIcon :name="item.icon" :size="13" class="text-cyan-300" />{{ item.label }}
                  </span>
                  <span class="text-[10px] text-emerald-300">{{ item.score }}%</span>
                </div>
                <div class="mt-1.5 flex items-center justify-between gap-2 text-[9px] text-slate-500">
                  <span class="truncate">{{ item.summary }}</span><span class="shrink-0 text-cyan-300/80">{{ item.metric }}</span>
                </div>
              </article>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-white/10 bg-[#0a1726] p-5">
          <h2 class="flex items-center gap-2 text-sm font-semibold">
            <SafeIcon name="Images" :size="17" class="text-amber-300" />
            处置前后效果
          </h2>
          <p class="mt-1 text-[10px] text-slate-500">现场反馈与 AI 原始证据同位置对照</p>
          <div class="mt-4 grid h-[210px] grid-cols-2 overflow-hidden rounded-xl border border-white/10">
            <div class="relative bg-[linear-gradient(145deg,#1b4c50,#2b7d7f_36%,#a27d51_37%,#6d5038_68%,#283b2c)]">
              <span class="absolute left-2 top-2 rounded bg-black/50 px-2 py-1 text-[9px]">处置前</span>
              <div class="absolute left-[32%] top-[52%] h-5 w-[48%] -rotate-12 rounded-full bg-[#c48b55]/70 shadow-[0_0_18px_rgba(255,93,93,.35)]" />
              <div class="absolute bottom-3 left-3 text-[10px] text-[#ffaaa5]">疑似开挖沟渠</div>
            </div>
            <div class="relative bg-[linear-gradient(145deg,#1b4c50,#2b7d7f_36%,#8c8f5e_37%,#526343_68%,#283b2c)]">
              <span class="absolute right-2 top-2 rounded bg-black/50 px-2 py-1 text-[9px]">处置后</span>
              <div class="absolute left-[32%] top-[52%] h-5 w-[48%] -rotate-12 rounded-full bg-emerald-300/25" />
              <div class="absolute bottom-3 right-3 flex items-center gap-1 text-[10px] text-emerald-300"><SafeIcon name="Check" :size="11" />风险已消除</div>
            </div>
          </div>
          <div class="mt-4 rounded-xl border border-emerald-300/15 bg-emerald-300/[0.05] p-3">
            <div class="flex items-center gap-2 text-xs font-medium text-emerald-200">
              <SafeIcon name="BadgeCheck" :size="15" />
              最终复核结论
            </div>
            <p class="mt-2 text-[11px] leading-relaxed text-slate-400">{{ review?.comment }}</p>
          </div>
        </article>
      </section>

      <ClosureTimeline
        :workorder="workorder"
        :timeline="timeline"
        :evidence="evidence"
        :review="review"
      />

      <section class="flex flex-col items-start justify-between gap-4 rounded-2xl border border-cyan-300/15 bg-gradient-to-r from-cyan-300/[0.07] to-blue-500/[0.05] p-5 sm:flex-row sm:items-center">
        <div>
          <h2 class="text-base font-semibold">案例结论：AI 发现结果已转化为可核验的治理成效</h2>
          <p class="mt-2 text-xs leading-relaxed text-slate-400">任务、证据、风险、建议、工单和复核记录形成统一 Case，实现全链路可追溯。</p>
        </div>
        <Button class="shrink-0 gap-2" @click="navigate(`./workorder-detail.html?orderId=${workorder.id}`)">
          <SafeIcon name="ExternalLink" :size="15" />
          查看完整闭环详情
        </Button>
      </section>
    </main>
  </div>
</template>

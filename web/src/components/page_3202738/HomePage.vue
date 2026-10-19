<script setup lang="ts">
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import CompetitionHero from '@/components/competition/CompetitionHero.vue'
import AiWorkflowRibbon from '@/components/competition/AiWorkflowRibbon.vue'
import CapabilityMetrics from '@/components/competition/CapabilityMetrics.vue'
import { competitionDemo } from '@/data/CompetitionDemoData'
import { resetCompetitionDemoState } from '@/lib/competition-demo-reset'
import { startCompetitionDemoSession } from '@/lib/competition-demo-session'
import { localAgentRuntime } from '@/lib/local-agent-runtime'

const caseHighlights = [
  { label: 'AI 任务', value: '近水沟渠筛查', icon: 'MessageSquareText' },
  { label: '证据融合', value: '影像 + 点云 + 时相', icon: 'Layers3' },
  { label: '风险输出', value: '高风险 1 · 待复核 1', icon: 'ShieldAlert' },
]

function navigateToTaskStudio(useDemo = false) {
  const params = new URLSearchParams()
  if (useDemo) {
    resetCompetitionDemoState()
    startCompetitionDemoSession()
    params.set('taskId', competitionDemo.taskId)
    params.set('sceneId', competitionDemo.sceneId)
  }
  const query = params.toString()
  window.location.href = `./task-studio.html${query ? `?${query}` : ''}`
}

async function navigateToRiskWorkspace() {
  resetCompetitionDemoState()
  startCompetitionDemoSession()
  await localAgentRuntime.createTask({
    taskId: competitionDemo.taskId,
    taskText: competitionDemo.taskText,
    sceneId: competitionDemo.sceneId,
    sampleId: competitionDemo.sceneSampleId,
    scenarioId: 'near-water-disturbance-workflow',
  })
  localAgentRuntime.complete(competitionDemo.taskId)
  const params = new URLSearchParams({
    taskId: competitionDemo.taskId,
    riskId: 'risk-agent-001',
  })
  window.location.href = `./risk-workspace.html?${params.toString()}`
}
</script>

<template>
  <main class="competition-home min-h-screen overflow-hidden bg-background text-foreground">
    <nav class="fixed inset-x-0 top-0 z-50 border-b border-white/[0.07] bg-[#07111f]/80 backdrop-blur-xl">
      <div class="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-5 md:px-8 lg:px-12">
        <a href="./index.html" class="flex items-center gap-3">
          <div class="grid h-9 w-9 place-items-center rounded-xl border border-primary/30 bg-primary/15 text-primary shadow-[0_0_20px_hsl(var(--primary)/0.16)]">
            <SafeIcon name="Waves" :size="20" />
          </div>
          <div>
            <div class="text-sm font-semibold leading-none text-foreground">HydroGuardian</div>
            <div class="mt-1 text-[10px] tracking-[0.18em] text-muted-foreground">水利智巡</div>
          </div>
        </a>

        <div class="hidden items-center gap-7 text-xs text-muted-foreground md:flex">
          <a href="#workflow" class="transition-colors hover:text-foreground">智能链路</a>
          <a href="#capabilities" class="transition-colors hover:text-foreground">核心能力</a>
          <button class="transition-colors hover:text-foreground" @click="navigateToRiskWorkspace">风险成果</button>
        </div>

        <Button size="sm" class="gap-2" @click="navigateToTaskStudio(true)">
          进入系统
          <SafeIcon name="ArrowRight" :size="14" />
        </Button>
      </div>
    </nav>

    <CompetitionHero
      @start-demo="navigateToTaskStudio(false)"
      @create-task="navigateToTaskStudio(false)"
    />

    <div id="workflow">
      <AiWorkflowRibbon />
    </div>

    <section class="px-5 py-14 md:px-8 lg:px-12">
      <div class="mx-auto grid max-w-[1440px] gap-8 overflow-hidden rounded-[28px] border border-white/10 bg-gradient-to-br from-primary/[0.09] via-card/50 to-accent/[0.06] p-6 md:p-9 lg:grid-cols-[1fr_0.9fr]">
        <div class="space-y-5">
          <div class="inline-flex items-center gap-2 text-xs font-medium text-accent">
            <SafeIcon name="BadgeCheck" :size="16" />
            典型案例 · 全链路智能处置
          </div>
          <h2 class="max-w-2xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl">从一句话，到一张可处置的风险工单</h2>
          <p class="max-w-2xl text-sm leading-7 text-muted-foreground">
            系统识别近水细长候选区域，结合点云高差与时相变化排除道路干扰；对证据冲突区域主动转人工复核，最终形成现场核查工单。
          </p>
          <div class="flex flex-wrap gap-3 pt-2">
            <Button class="gap-2" @click="navigateToTaskStudio(true)">
              <SafeIcon name="PlayCircle" :size="17" />
              运行完整案例
            </Button>
            <Button variant="outline" class="gap-2 border-white/15 bg-transparent" @click="navigateToRiskWorkspace">
              查看研判成果
              <SafeIcon name="ArrowUpRight" :size="16" />
            </Button>
          </div>
        </div>

        <div class="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
          <div v-for="item in caseHighlights" :key="item.label" class="flex items-center gap-4 rounded-2xl border border-white/[0.08] bg-black/10 p-4">
            <div class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent/10 text-accent">
              <SafeIcon :name="item.icon" :size="19" />
            </div>
            <div class="min-w-0">
              <p class="text-[11px] text-muted-foreground">{{ item.label }}</p>
              <p class="mt-1 truncate text-sm font-medium text-card-foreground">{{ item.value }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <div id="capabilities">
      <CapabilityMetrics />
    </div>

    <footer class="border-t border-white/[0.07] px-5 py-8 md:px-8 lg:px-12">
      <div class="mx-auto flex max-w-[1440px] flex-col gap-4 text-xs text-muted-foreground md:flex-row md:items-center md:justify-between">
        <div class="flex items-center gap-2">
          <SafeIcon name="Waves" :size="15" class="text-primary" />
          <span>HydroGuardian 水利智巡 · 多智能体水利隐患发现与闭环处置系统</span>
        </div>
        <span>自然语言驱动 · 多模态证据 · 安全可解释</span>
      </div>
    </footer>
  </main>
</template>

<style scoped>
.competition-home {
  background-image:
    radial-gradient(circle at 72% 12%, hsl(var(--primary) / .08), transparent 28%),
    radial-gradient(circle at 18% 42%, hsl(var(--accent) / .045), transparent 32%);
}
</style>

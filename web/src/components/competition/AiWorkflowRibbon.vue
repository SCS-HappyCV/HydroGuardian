<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'

const stages = [
  { index: '01', icon: 'MessageSquareText', title: '自然语言任务', description: '理解目标与巡查意图', color: 'primary' },
  { index: '02', icon: 'Braces', title: '空间程序编译', description: '生成约束与执行步骤', color: 'violet' },
  { index: '03', icon: 'Layers3', title: '多模态证据', description: '影像、点云、时相融合', color: 'accent' },
  { index: '04', icon: 'ScanSearch', title: '风险研判', description: '解释、排序与主动弃权', color: 'warning' },
  { index: '05', icon: 'ClipboardCheck', title: '处置闭环', description: '建议、工单与人工复核', color: 'success' },
]
</script>

<template>
  <section class="px-5 py-16 md:px-8 lg:px-12">
    <div class="mx-auto max-w-[1440px]">
      <div class="mb-9 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p class="mb-2 text-xs font-semibold uppercase tracking-[0.24em] text-accent">AI WORKFLOW</p>
          <h2 class="text-3xl font-semibold tracking-tight text-foreground md:text-4xl">一条可执行、可解释、可追溯的智能链路</h2>
        </div>
        <p class="max-w-md text-sm leading-6 text-muted-foreground">每一步都保留任务参数、证据来源与风险判断，避免黑盒式输出。</p>
      </div>

      <div class="workflow-shell grid gap-3 rounded-[24px] border border-white/10 bg-card/35 p-3 backdrop-blur-xl md:grid-cols-5">
        <div v-for="(stage, index) in stages" :key="stage.index" class="relative min-w-0">
          <div class="group h-full rounded-2xl border border-transparent bg-white/[0.025] p-5 transition-colors hover:border-white/10 hover:bg-white/[0.045]">
            <div class="mb-8 flex items-center justify-between">
              <div :class="['stage-icon', `stage-icon-${stage.color}`]">
                <SafeIcon :name="stage.icon" :size="20" />
              </div>
              <span class="font-mono text-[11px] text-muted-foreground/55">{{ stage.index }}</span>
            </div>
            <h3 class="text-sm font-semibold text-foreground">{{ stage.title }}</h3>
            <p class="mt-2 text-xs leading-5 text-muted-foreground">{{ stage.description }}</p>
          </div>
          <div v-if="index < stages.length - 1" class="workflow-arrow absolute -right-3 top-1/2 z-10 hidden h-px w-3 bg-gradient-to-r from-primary/20 to-accent/70 md:block" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.workflow-shell { box-shadow: 0 24px 80px rgba(0, 0, 0, .18), inset 0 1px 0 rgba(255, 255, 255, .035); }
.stage-icon { display: grid; height: 42px; width: 42px; place-items: center; border-radius: 12px; }
.stage-icon-primary { background: hsl(var(--primary) / .14); color: hsl(var(--primary)); }
.stage-icon-violet { background: rgba(139, 124, 255, .14); color: #a99fff; }
.stage-icon-accent { background: hsl(var(--accent) / .14); color: hsl(var(--accent)); }
.stage-icon-warning { background: hsl(var(--warning) / .14); color: hsl(var(--warning)); }
.stage-icon-success { background: hsl(var(--success) / .14); color: hsl(var(--success)); }
</style>


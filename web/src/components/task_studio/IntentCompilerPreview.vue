<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { compileTaskIntent } from '@/lib/task-intent-compiler'

const props = defineProps<{
  taskText: string
  zoneName?: string
  priority?: string
  sceneId?: string
  isExecuting?: boolean
  executionProgress?: number
  executionStage?: string
  actionLabel?: string
}>()

defineEmits<{
  execute: []
}>()

const intent = computed(() => compileTaskIntent(props.taskText))
const hasTask = computed(() => Boolean(props.taskText.trim()))

const priorityLabel = computed(() => ({ high: '高', medium: '中', low: '低' }[props.priority || ''] || '未设置'))
</script>

<template>
  <section class="intent-panel overflow-hidden rounded-2xl border border-accent/20 bg-card/70 shadow-card backdrop-blur-xl">
    <div class="border-b border-white/[0.07] bg-gradient-to-r from-accent/[0.10] to-primary/[0.06] p-5">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="flex items-center gap-2 text-sm font-semibold text-foreground">
            <span class="grid h-8 w-8 place-items-center rounded-lg bg-accent/15 text-accent">
              <SafeIcon name="Braces" :size="17" />
            </span>
            AI 意图编译
          </div>
          <p class="mt-2 text-xs leading-5 text-muted-foreground">自然语言正在转换为可执行空间任务</p>
        </div>
        <span class="rounded-full border border-accent/20 bg-accent/10 px-2.5 py-1 text-[10px] font-medium text-accent">
          {{ hasTask ? '解析就绪' : '等待输入' }}
        </span>
      </div>
    </div>

    <div v-if="hasTask" class="space-y-5 p-5">
      <div class="rounded-xl border border-white/[0.07] bg-black/10 p-4">
        <p class="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">EXECUTABLE OBJECTIVE</p>
        <p class="mt-2 text-sm font-medium leading-6 text-card-foreground">{{ intent.objective }}</p>
      </div>

      <div class="grid grid-cols-2 gap-3 text-xs">
        <div class="intent-field">
          <span>目标对象</span>
          <strong>{{ intent.target }}</strong>
        </div>
        <div class="intent-field">
          <span>巡查区域</span>
          <strong>{{ zoneName || '未指定' }}</strong>
        </div>
        <div class="intent-field">
          <span>任务优先级</span>
          <strong>{{ priorityLabel }}</strong>
        </div>
        <div class="intent-field">
          <span>排序规则</span>
          <strong>{{ intent.ranking }}</strong>
        </div>
      </div>

      <div class="space-y-3">
        <div class="intent-list">
          <div class="intent-list-title"><SafeIcon name="MapPin" :size="14" />空间关系</div>
          <div class="flex flex-wrap gap-1.5"><span v-for="item in intent.spatialRelations" :key="item">{{ item }}</span></div>
        </div>
        <div class="intent-list">
          <div class="intent-list-title"><SafeIcon name="Shapes" :size="14" />几何约束</div>
          <div class="flex flex-wrap gap-1.5"><span v-for="item in intent.geometryConstraints" :key="item">{{ item }}</span></div>
        </div>
        <div class="intent-list">
          <div class="intent-list-title"><SafeIcon name="CircleOff" :size="14" />排除条件</div>
          <div class="flex flex-wrap gap-1.5"><span v-for="item in intent.exclusions" :key="item">{{ item }}</span></div>
        </div>
        <div class="intent-list">
          <div class="intent-list-title"><SafeIcon name="Layers3" :size="14" />证据模态</div>
          <div class="flex flex-wrap gap-1.5"><span v-for="item in intent.evidenceModalities" :key="item">{{ item }}</span></div>
        </div>
      </div>

      <div class="flex gap-2 rounded-xl border border-violet-400/15 bg-violet-400/[0.06] p-3 text-xs leading-5 text-violet-200">
        <SafeIcon name="ShieldCheck" :size="16" class="mt-0.5 shrink-0" />
        <span>{{ intent.reviewPolicy }}</span>
      </div>

      <div v-if="isExecuting" class="space-y-2 rounded-xl border border-primary/15 bg-primary/[0.05] p-3">
        <div class="flex justify-between text-[11px] text-muted-foreground">
          <span>{{ executionStage }}</span><span>{{ Math.round(executionProgress || 0) }}%</span>
        </div>
        <div class="h-1.5 overflow-hidden rounded-full bg-muted"><div class="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all" :style="{ width: `${executionProgress || 0}%` }" /></div>
      </div>

      <Button class="h-11 w-full gap-2" :disabled="isExecuting" @click="$emit('execute')">
        <SafeIcon v-if="!isExecuting" name="Play" :size="17" />
        <span v-else class="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground" />
        {{ isExecuting ? '正在生成 Agent 决策...' : actionLabel || '确认并启动智能巡查' }}
      </Button>

      <p class="truncate text-center text-[10px] text-muted-foreground/70">场景：{{ sceneId || '待选择' }}</p>
    </div>

    <div v-else class="grid min-h-[420px] place-items-center p-8 text-center">
      <div>
        <div class="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-muted/40 text-muted-foreground">
          <SafeIcon name="MessageSquareText" :size="25" />
        </div>
        <p class="mt-4 text-sm font-medium text-card-foreground">输入巡查目标后开始编译</p>
        <p class="mx-auto mt-2 max-w-xs text-xs leading-5 text-muted-foreground">系统将自动识别目标、空间关系、几何约束和所需证据。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.intent-field { display: flex; min-width: 0; flex-direction: column; gap: 5px; border: 1px solid rgba(255,255,255,.065); border-radius: 10px; background: rgba(255,255,255,.018); padding: 10px; }
.intent-field span { color: hsl(var(--muted-foreground)); font-size: 10px; }
.intent-field strong { overflow: hidden; color: hsl(var(--card-foreground)); font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.intent-list { display: grid; gap: 8px; }
.intent-list-title { display: flex; align-items: center; gap: 6px; color: hsl(var(--muted-foreground)); font-size: 11px; }
.intent-list span { border: 1px solid hsl(var(--primary) / .14); border-radius: 6px; background: hsl(var(--primary) / .07); padding: 4px 7px; color: hsl(var(--card-foreground)); font-size: 10px; }
</style>

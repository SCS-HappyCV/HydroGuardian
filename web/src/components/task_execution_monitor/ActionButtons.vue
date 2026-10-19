<!-- 任务操作区：根据任务状态展示停止、重试、修改参数、查看结果和系统健康入口。 -->
<script setup lang="ts">
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

defineProps<{
  status: string
  isRunning: boolean
  isSuccess: boolean
  isFailed: boolean
  isQueued: boolean
  canViewResults?: boolean
  canExportReport?: boolean
}>()

const emit = defineEmits<{
  (e: 'stop'): void
  (e: 'retry'): void
  (e: 'modify-params'): void
  (e: 'view-results'): void
  (e: 'view-system-health'): void
  (e: 'export-report'): void
}>()
</script>

<template>
  <div class="surface-base card-padding flex flex-wrap items-center gap-3">
    <template v-if="isRunning">
      <Button
        variant="destructive"
        class="gap-2"
        @click="emit('stop')"
      >
        <SafeIcon name="Square" :size="16" />
        停止任务
      </Button>
      <p class="text-xs text-muted-foreground">
        任务正在执行中，点击停止按钮可中断任务。
      </p>
    </template>

    <template v-else-if="isSuccess">
      <Button
        v-if="canViewResults !== false"
        class="gap-2 bg-[hsl(var(--success))] hover:bg-[hsl(var(--success))]/90 text-white"
        @click="emit('view-results')"
      >
        <SafeIcon name="Eye" :size="16" />
        查看风险结果
      </Button>
      <Button v-if="canExportReport" variant="outline" class="gap-2" @click="emit('export-report')">
        <SafeIcon name="FileCheck2" :size="16" />
        生成审计报告
      </Button>
      <p class="text-xs text-muted-foreground">
        {{ canViewResults === false ? '真实专家执行完成，结果产物可在证据产物流中下载。' : '任务执行成功，可查看生成的风险分析结果。' }}
      </p>
    </template>

    <template v-else-if="isFailed">
      <Button
        class="gap-2"
        @click="emit('retry')"
      >
        <SafeIcon name="RotateCcw" :size="16" />
        重新执行
      </Button>
      <Button
        variant="outline"
        class="gap-2"
        @click="emit('modify-params')"
      >
        <SafeIcon name="Edit2" :size="16" />
        修改参数
      </Button>
      <Button
        variant="ghost"
        class="gap-2 text-destructive hover:text-destructive hover:bg-destructive/10"
        @click="emit('view-system-health')"
      >
        <SafeIcon name="AlertTriangle" :size="16" />
        查看系统状态
      </Button>
      <p class="text-xs text-muted-foreground">
        任务执行失败，可重试或检查系统健康状态。
      </p>
    </template>

    <template v-else-if="isQueued">
      <Button variant="destructive" class="gap-2" @click="emit('stop')">
        <SafeIcon name="Square" :size="16" />
        取消任务
      </Button>
      <Button
        variant="outline"
        class="gap-2"
        @click="emit('modify-params')"
      >
        <SafeIcon name="Edit2" :size="16" />
        修改参数
      </Button>
      <p class="text-xs text-muted-foreground">
        任务已提交，Planner 将在资源可用后生成执行路径。
      </p>
    </template>

    <template v-else-if="status === 'blocked'">
      <Button class="gap-2" @click="emit('retry')"><SafeIcon name="RotateCcw" :size="16" />能力恢复后重试</Button>
      <Button variant="outline" class="gap-2" @click="emit('modify-params')"><SafeIcon name="Edit2" :size="16" />调整任务</Button>
      <Button variant="ghost" class="gap-2" @click="emit('view-system-health')"><SafeIcon name="ServerCog" :size="16" />查看专家状态</Button>
      <p class="text-xs text-muted-foreground">执行路径已保留，所需专家能力当前不可用。</p>
    </template>

    <template v-else-if="status === 'cancelled'">
      <Button class="gap-2" @click="emit('retry')"><SafeIcon name="RotateCcw" :size="16" />重新提交</Button>
      <Button variant="outline" class="gap-2" @click="emit('modify-params')"><SafeIcon name="Edit2" :size="16" />调整任务</Button>
      <p class="text-xs text-muted-foreground">任务已取消，已生成的证据产物仍然保留。</p>
    </template>

    <template v-else-if="status === 'clarification_required' || status === 'abstained'">
      <Button class="gap-2" @click="emit('modify-params')"><SafeIcon name="MessageSquareMore" :size="16" />补充任务信息</Button>
      <p class="text-xs text-muted-foreground">Agent 未强行执行，请补充数据或调整任务描述后重新提交。</p>
    </template>
  </div>
</template>

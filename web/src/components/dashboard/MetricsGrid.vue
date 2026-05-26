
<script setup lang="ts">
import StatCard from '@/components/common/StatCard.vue'

interface Props {
  todayTasks: number
  completionRate: number
  failedTasks: number
  totalRiskCount: number
  highRiskCount: number
  pendingWorkorders: number
  reviewWorkorders: number
}

const props = defineProps<Props>()

const failureRate = computed(() => {
  if (props.todayTasks === 0) return 0
  return Math.round((props.failedTasks / props.todayTasks) * 100)
})
</script>

<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
    <StatCard
      icon="CheckCircle2"
      label="今日完成率"
      :value="`${completionRate}%`"
      color="primary"
      href="./task-studio.html"
      :trend="{ value: 12, direction: 'up' }"
    />
    
    <StatCard
      icon="AlertTriangle"
      label="失败任务"
      :value="failedTasks"
      color="destructive"
      href="./system-health.html"
      :trend="{ value: 5, direction: 'down' }"
    />
    
    <StatCard
      icon="Activity"
      label="风险事件总数"
      :value="totalRiskCount"
      color="warning"
      href="./risk-workspace.html"
      :trend="{ value: 8, direction: 'up' }"
    />
    
    <StatCard
      icon="AlertTriangle"
      label="高风险点位"
      :value="highRiskCount"
      color="destructive"
      href="./risk-workspace.html?riskLevel=high"
      :trend="{ value: 3, direction: 'up' }"
    />
    
    <StatCard
      icon="ClipboardList"
      label="待处理工单"
      :value="pendingWorkorders"
      color="accent"
      href="./workorder-center.html?status=todo"
      :trend="{ value: 2, direction: 'down' }"
    />
    
    <StatCard
      icon="SearchCheck"
      label="待复核工单"
      :value="reviewWorkorders"
      color="warning"
      href="./workorder-center.html?status=review"
    />
  </div>
</template>

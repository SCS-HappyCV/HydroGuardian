
<script setup lang="ts">
import { computed } from 'vue'
import { query as queryTasks } from '@/data/TaskService'
import { query as queryRiskEvents } from '@/data/RiskEventService'
import { query as queryWorkorders } from '@/data/WorkorderService'
import MetricsGrid from './MetricsGrid.vue'
import RiskDistribution from './RiskDistribution.vue'
import RecentTasksList from './RecentTasksList.vue'
import RiskHeatmapPreview from './RiskHeatmapPreview.vue'
import AlertBanner from './AlertBanner.vue'
import { remoteAgentApi } from '@/api/remote-agent-api'
import { mapRemoteTask, restoreRemoteTaskBinding } from '@/lib/remote-task-history'
import { getRemoteAgentSnapshots } from '@/lib/remote-agent-storage'
import { buildRisksFromAgentSnapshot } from '@/lib/agent-risk-presentation'

const isClient = ref(true)

const tasks = ref(queryTasks({}))
const riskEvents = ref(queryRiskEvents({}))
const workorders = ref(queryWorkorders({}))

const todayTasks = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return tasks.value.filter(t => {
    const createdDate = new Date(t.createdAt)
    createdDate.setHours(0, 0, 0, 0)
    return createdDate.getTime() === today.getTime()
  })
})

const completedTasks = computed(() => todayTasks.value.filter(t => t.status === 'success').length)
const failedTasks = computed(() => todayTasks.value.filter(t => t.status === 'failed').length)
const completionRate = computed(() => {
  if (todayTasks.value.length === 0) return 0
  return Math.round((completedTasks.value / todayTasks.value.length) * 100)
})

const highRiskCount = computed(() => riskEvents.value.filter(r => r.level === 'high').length)
const mediumRiskCount = computed(() => riskEvents.value.filter(r => r.level === 'medium').length)
const lowRiskCount = computed(() => riskEvents.value.filter(r => r.level === 'low').length)
const reviewRequiredCount = computed(() => riskEvents.value.filter(r => r.level === 'review_required').length)
const totalRiskCount = computed(() => riskEvents.value.length)

const pendingWorkorders = computed(() => workorders.value.filter(w => w.status === 'todo').length)
const reviewWorkorders = computed(() => workorders.value.filter(w => w.status === 'review').length)

const systemStatus = ref<'normal' | 'warning' | 'error'>('normal')

const recentTasks = computed(() => {
  return [...tasks.value]
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    .slice(0, 5)
})

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(async () => {
    const snapshotRisks = getRemoteAgentSnapshots().flatMap(snapshot => buildRisksFromAgentSnapshot(snapshot))
    const remoteRiskIds = new Set(snapshotRisks.map(risk => risk.id))
    riskEvents.value = [...snapshotRisks, ...queryRiskEvents({}).filter(risk => !remoteRiskIds.has(risk.id))]
    try {
      const remoteTasks = await remoteAgentApi.listTasks({ limit: '100' })
      remoteTasks.forEach(restoreRemoteTaskBinding)
      const remoteIds = new Set(remoteTasks.map((task) => task.task_id))
      tasks.value = [...remoteTasks.map(mapRemoteTask), ...queryTasks({}).filter((task) => !remoteIds.has(task.id))]
    } catch {
      tasks.value = queryTasks({})
    }
    isClient.value = true
  })
})
</script>

<template>
  <div v-if="isClient" class="page-body space-y-6 pb-8">
    <AlertBanner v-if="systemStatus === 'error'" />

    <div class="space-y-2">
      <h1 class="text-page-title">全局总览</h1>
      <p class="text-body">实时监控系统运行态势与风险分布</p>
    </div>

    <MetricsGrid 
      :today-tasks="todayTasks.length"
      :completion-rate="completionRate"
      :failed-tasks="failedTasks"
      :total-risk-count="totalRiskCount"
      :high-risk-count="highRiskCount"
      :pending-workorders="pendingWorkorders"
      :review-workorders="reviewWorkorders"
    />

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div>
        <RiskHeatmapPreview :risks="riskEvents" />
      </div>
      <div class="lg:col-span-2">
        <RiskDistribution 
          :high="highRiskCount"
          :medium="mediumRiskCount"
          :low="lowRiskCount"
          :review-required="reviewRequiredCount"
        />
      </div>
    </div>

    <RecentTasksList :tasks="recentTasks" />
  </div>
</template>

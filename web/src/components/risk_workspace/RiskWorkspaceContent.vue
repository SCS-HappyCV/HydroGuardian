
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { toast } from 'vue-sonner'
import * as RiskEventService from '@/data/RiskEventService'
import * as ZoneService from '@/data/ZoneService'
import * as RiskLayerService from '@/data/RiskLayerService'
import * as TaskService from '@/data/TaskService'
import type { RiskEventData } from '@/data/RiskEventData'
import type { ZoneData } from '@/data/ZoneData'
import type { RiskLayerData } from '@/data/RiskLayerData'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import SafeIcon from '@/components/common/SafeIcon.vue'
import RiskMap from './RiskMap.vue'
import RiskLayerPanel from './RiskLayerPanel.vue'
import RiskDetailCard from './RiskDetailCard.vue'
import RiskListTable from './RiskListTable.vue'
import { cn } from '@/lib/utils'

const isClient = ref(true)

const allRisks = ref(RiskEventService.getAll())
const allZones = ref(ZoneService.getAll())
const allLayers = ref(RiskLayerService.getAll())

const taskId = ref<string | null>(null)
const zoneId = ref<string | null>(null)
const riskLevelFilter = ref<string>('all')
const sortBy = ref<'level' | 'score' | 'time'>('level')
const selectedRiskId = ref<string | null>(null)

const currentTask = computed(() => {
  return taskId.value ? TaskService.getById(taskId.value) : null
})

const filteredRisks = computed(() => {
  let result = allRisks.value || []

  if (taskId.value) {
    result = result.filter(r => r.taskId === taskId.value)
  }

  if (zoneId.value) {
    result = result.filter(r => r.zoneId === zoneId.value)
  }

  if (riskLevelFilter.value !== 'all') {
    result = result.filter(r => r.level === riskLevelFilter.value)
  }

  return result.sort((a, b) => {
    if (sortBy.value === 'level') {
      const levelOrder = { high: 0, medium: 1, low: 2, review_required: 3 }
      return levelOrder[a.level as keyof typeof levelOrder] - levelOrder[b.level as keyof typeof levelOrder]
    } else if (sortBy.value === 'score') {
      return b.score - a.score
    } else {
      return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    }
  })
})

const selectedRisk = computed(() => {
  return selectedRiskId.value ? RiskEventService.getById(selectedRiskId.value) : filteredRisks.value[0] || null
})

const riskStats = computed(() => {
  const risks = filteredRisks.value || []
  return {
    high: risks.filter(r => r.level === 'high').length,
    medium: risks.filter(r => r.level === 'medium').length,
    low: risks.filter(r => r.level === 'low').length,
    reviewRequired: risks.filter(r => r.level === 'review_required').length,
  }
})

const handleMapClick = (riskId: string) => {
  selectedRiskId.value = riskId
}

const handleTableRowClick = (risk: RiskEventData) => {
  selectedRiskId.value = risk.id
}

const handleCreateWorkorder = () => {
  if (selectedRisk.value) {
    window.location.href = `./workorder-center.html?riskId=${selectedRisk.value.id}`
  }
}

const handleMarkReview = () => {
  if (selectedRisk.value && selectedRisk.value.status !== 'review_required') {
    const updatedRisk = { ...selectedRisk.value, status: 'review_required' as const }
    const index = allRisks.value.findIndex(r => r.id === selectedRisk.value!.id)
    if (index >= 0) {
      allRisks.value[index] = updatedRisk
    }
    toast.success('已标记为待复核')
  }
}

const handleReturnToExecution = () => {
  if (taskId.value) {
    window.location.href = `./task-execution-monitor.html?taskId=${taskId.value}`
  }
}

const handleGoHome = () => {
  window.location.href = './dashboard.html'
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    const params = new URLSearchParams(window.location.search)
    const paramTaskId = params.get('taskId')
    const paramZoneId = params.get('zoneId')
    const paramRiskLevel = params.get('riskLevel')

    if (paramTaskId) taskId.value = paramTaskId
    if (paramZoneId) zoneId.value = paramZoneId
    if (paramRiskLevel && ['high', 'medium', 'low', 'review_required'].includes(paramRiskLevel)) {
      riskLevelFilter.value = paramRiskLevel
    }

    if (!selectedRiskId.value && (filteredRisks.value || []).length > 0) {
      selectedRiskId.value = (filteredRisks.value || [])[0].id
    }

    isClient.value = true
  })
})
</script>

<template>
  <div v-if="isClient" class="flex flex-col h-full bg-background overflow-hidden">
    <!-- Header with breadcrumb and actions -->
    <div class="flex-shrink-0 border-b border-border/50 bg-background/50 backdrop-blur-sm px-6 py-4">
      <div class="flex items-center justify-between gap-4 mb-3">
        <div class="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            class="h-8 w-8"
            @click="handleGoHome"
            title="返回首页"
          >
            <SafeIcon name="Home" :size="18" />
          </Button>
          <span class="text-sm text-muted-foreground">/</span>
          <h1 class="text-xl font-semibold text-foreground">风险分析工作区</h1>
        </div>

        <div class="flex items-center gap-2">
          <Button
            v-if="taskId"
            variant="outline"
            size="sm"
            class="gap-2"
            @click="handleReturnToExecution"
          >
            <SafeIcon name="ArrowLeft" :size="14" />
            返回执行日志
          </Button>
        </div>
      </div>

      <!-- Filter bar -->
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2">
          <span class="text-sm text-muted-foreground">风险等级:</span>
          <Select v-model="riskLevelFilter">
            <SelectTrigger class="w-[140px] h-8 bg-card/50 text-sm">
              <SelectValue placeholder="全部" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="high">高风险</SelectItem>
              <SelectItem value="medium">中风险</SelectItem>
              <SelectItem value="low">低风险</SelectItem>
              <SelectItem value="review_required">待复核</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="flex items-center gap-2">
          <span class="text-sm text-muted-foreground">排序:</span>
          <Select v-model="sortBy">
            <SelectTrigger class="w-[140px] h-8 bg-card/50 text-sm">
              <SelectValue placeholder="按等级" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="level">按等级</SelectItem>
              <SelectItem value="score">按分数</SelectItem>
              <SelectItem value="time">按更新时间</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="flex items-center gap-2 ml-auto text-sm text-muted-foreground">
          <span>高: {{ riskStats.high }}</span>
          <span class="text-muted-foreground/40">|</span>
          <span>中: {{ riskStats.medium }}</span>
          <span class="text-muted-foreground/40">|</span>
          <span>低: {{ riskStats.low }}</span>
          <span class="text-muted-foreground/40">|</span>
          <span>待复核: {{ riskStats.reviewRequired }}</span>
        </div>
      </div>
    </div>

    <!-- Main content area: map + layers + list + detail -->
    <div class="flex-1 min-h-0 overflow-hidden flex gap-4 p-4">
      <!-- Left: Map and layers -->
      <div class="flex-1 min-w-0 flex flex-col gap-3">
        <!-- Map container (full-bleed: no padding intentional) -->
        <div class="flex-1 min-h-0 rounded-[--radius] border border-border overflow-hidden bg-muted/20">
          <RiskMap
            :risks="filteredRisks"
            :zones="allZones"
            :selected-risk-id="selectedRiskId"
            :zone-id="zoneId"
            @risk-click="handleMapClick"
          />
        </div>

        <!-- Layer panel -->
        <div class="flex-shrink-0">
          <RiskLayerPanel :layers="allLayers" />
        </div>
      </div>

      <!-- Right: List and detail -->
      <div class="w-96 flex flex-col gap-3 min-w-0">
        <!-- Risk list table -->
        <div class="flex-1 min-h-0 overflow-hidden rounded-[--radius] border border-border bg-card/40">
          <RiskListTable
            :risks="filteredRisks"
            :selected-risk-id="selectedRiskId"
            @row-click="handleTableRowClick"
          />
        </div>

        <!-- Detail card -->
        <div v-if="selectedRisk" class="flex-shrink-0">
          <RiskDetailCard
            :risk="selectedRisk"
            @create-workorder="handleCreateWorkorder"
            @mark-review="handleMarkReview"
          />
        </div>
      </div>
    </div>
  </div>

  <!-- Loading state during hydration -->
  <div v-else class="h-full flex items-center justify-center bg-background">
    <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
  </div>
</template>

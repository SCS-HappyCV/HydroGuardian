
<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import SafeIcon from '@/components/common/SafeIcon.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { toast } from 'vue-sonner'
import * as TaskService from '@/data/TaskService'
import * as RiskEventService from '@/data/RiskEventService'
import type { TaskData } from '@/data/TaskData'
import type { RiskEventData } from '@/data/RiskEventData'
import RiskDiffCard from './RiskDiffCard.vue'

const tasks = ref(TaskService.getAll())
const allRisks = ref(RiskEventService.getAll())
const isClient = ref(true)

const selectedTaskIds = ref<[string, string] | null>(null)
const activeTab = ref<'overview' | 'new' | 'disappeared' | 'changed'>('overview')

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    const params = new URLSearchParams(window.location.search)
    const taskIdsParam = params.get('taskIds')
    
    if (taskIdsParam) {
      try {
        const parsed = JSON.parse(taskIdsParam)
        if (Array.isArray(parsed) && parsed.length >= 2) {
          selectedTaskIds.value = [parsed[0], parsed[1]]
        }
      } catch {
        const ids = taskIdsParam.split(',').slice(0, 2)
        if (ids.length >= 2) {
          selectedTaskIds.value = [ids[0], ids[1]]
        }
      }
    }

    if (!selectedTaskIds.value) {
      const successTasks = tasks.value.filter(t => t.status === 'success')
      if (successTasks.length >= 2) {
        selectedTaskIds.value = [successTasks[0].id, successTasks[1].id]
      } else if (tasks.value.length >= 2) {
        selectedTaskIds.value = [tasks.value[0].id, tasks.value[1].id]
      }
    }

    isClient.value = true
  })
})

const successTasks = computed(() => tasks.value.filter(t => t.status === 'success'))

const task1 = computed(() => selectedTaskIds.value ? tasks.value.find(t => t.id === selectedTaskIds.value![0]) : null)
const task2 = computed(() => selectedTaskIds.value ? tasks.value.find(t => t.id === selectedTaskIds.value![1]) : null)

const risks1 = computed(() => {
  if (!selectedTaskIds.value) return []
  return allRisks.value.filter(r => r.taskId === selectedTaskIds.value![0])
})

const risks2 = computed(() => {
  if (!selectedTaskIds.value) return []
  return allRisks.value.filter(r => r.taskId === selectedTaskIds.value![1])
})

const newRisks = computed(() => {
  const risk1Ids = new Set(risks1.value.map(r => r.id))
  return risks2.value.filter(r => !risk1Ids.has(r.id))
})

const disappearedRisks = computed(() => {
  const risk2Ids = new Set(risks2.value.map(r => r.id))
  return risks1.value.filter(r => !risk2Ids.has(r.id))
})

const changedRisks = computed(() => {
  const riskMap1 = new Map(risks1.value.map(r => [r.id, r]))
  return risks2.value
    .filter(r => riskMap1.has(r.id) && riskMap1.get(r.id)!.score !== r.score)
    .map(r => ({
      old: riskMap1.get(r.id)!,
      new: r
    }))
})

const handleTaskChange = (index: 1 | 2, taskId: string) => {
  if (!selectedTaskIds.value) return
  const newIds: [string, string] = index === 1 ? [taskId, selectedTaskIds.value[1]] : [selectedTaskIds.value[0], taskId]
  selectedTaskIds.value = newIds
}

const handleReselect = () => {
  window.location.href = './history.html'
}

const handleExport = () => {
  toast.success('对比报告已导出')
}

const totalChanges = computed(() => newRisks.value.length + disappearedRisks.value.length + changedRisks.value.length)
</script>

<template>
  <div v-if="isClient" class="page-body space-y-6">
    <!-- Task Selector -->
    <div class="surface-base card-padding">
      <div class="flex flex-col gap-4">
        <div class="flex items-center justify-between">
          <h3 class="text-section-title">选择对比任务</h3>
          <Button variant="outline" size="sm" @click="handleReselect" class="gap-2">
            <SafeIcon name="RotateCcw" :size="14" />
            重新选择
          </Button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="space-y-2">
            <label class="text-label">任务 1（基准）</label>
            <Select :model-value="selectedTaskIds?.[0] || ''" @update:model-value="(val) => handleTaskChange(1, val)">
              <SelectTrigger class="bg-card/50">
                <SelectValue placeholder="选择任务 1" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="task in successTasks" :key="task.id" :value="task.id">
                  {{ task.name }} ({{ new Date(task.finishedAt || '').toLocaleDateString('zh-CN') }})
                </SelectItem>
              </SelectContent>
            </Select>
            <p v-if="task1" class="text-caption text-muted-foreground">
              {{ task1.inputText }}
            </p>
          </div>

          <div class="space-y-2">
            <label class="text-label">任务 2（对比）</label>
            <Select :model-value="selectedTaskIds?.[1] || ''" @update:model-value="(val) => handleTaskChange(2, val)">
              <SelectTrigger class="bg-card/50">
                <SelectValue placeholder="选择任务 2" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="task in successTasks" :key="task.id" :value="task.id">
                  {{ task.name }} ({{ new Date(task.finishedAt || '').toLocaleDateString('zh-CN') }})
                </SelectItem>
              </SelectContent>
            </Select>
            <p v-if="task2" class="text-caption text-muted-foreground">
              {{ task2.inputText }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Comparison Summary -->
    <div v-if="selectedTaskIds && (task1 || task2)" class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <Card class="surface-base border-border">
        <CardContent class="pt-6">
          <div class="space-y-2">
            <p class="text-caption text-muted-foreground">新增风险</p>
            <p class="text-3xl font-bold text-destructive">{{ newRisks.length }}</p>
          </div>
        </CardContent>
      </Card>

      <Card class="surface-base border-border">
        <CardContent class="pt-6">
          <div class="space-y-2">
            <p class="text-caption text-muted-foreground">消失风险</p>
            <p class="text-3xl font-bold text-[hsl(var(--success))]">{{ disappearedRisks.length }}</p>
          </div>
        </CardContent>
      </Card>

      <Card class="surface-base border-border">
        <CardContent class="pt-6">
          <div class="space-y-2">
            <p class="text-caption text-muted-foreground">变化风险</p>
            <p class="text-3xl font-bold text-[hsl(var(--warning))]">{{ changedRisks.length }}</p>
          </div>
        </CardContent>
      </Card>

      <Card class="surface-base border-border">
        <CardContent class="pt-6">
          <div class="space-y-2">
            <p class="text-caption text-muted-foreground">总变化</p>
            <p class="text-3xl font-bold text-primary">{{ totalChanges }}</p>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Comparison Tabs -->
    <div v-if="selectedTaskIds && totalChanges > 0" class="surface-base">
      <Tabs :model-value="activeTab" @update:model-value="(val) => activeTab = val as any" class="w-full">
        <div class="border-b border-border px-6 pt-4">
          <TabsList class="bg-transparent border-b-0 gap-8 h-auto p-0">
            <TabsTrigger 
              value="overview" 
              class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-0 py-2 text-sm font-medium"
            >
              总体对比
            </TabsTrigger>
            <TabsTrigger 
              value="new" 
              class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-0 py-2 text-sm font-medium"
            >
              新增 ({{ newRisks.length }})
            </TabsTrigger>
            <TabsTrigger 
              value="disappeared" 
              class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-0 py-2 text-sm font-medium"
            >
              消失 ({{ disappearedRisks.length }})
            </TabsTrigger>
            <TabsTrigger 
              value="changed" 
              class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-0 py-2 text-sm font-medium"
            >
              变化 ({{ changedRisks.length }})
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" class="card-padding space-y-4">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="space-y-3">
              <h4 class="text-item-title text-destructive flex items-center gap-2">
                <SafeIcon name="Plus" :size="16" />
                新增风险点 ({{ newRisks.length }})
              </h4>
              <div class="space-y-2 max-h-96 overflow-y-auto">
                <RiskDiffCard 
                  v-for="risk in newRisks.slice(0, 5)" 
                  :key="risk.id" 
                  :risk="risk" 
                  type="new"
                />
                <p v-if="newRisks.length > 5" class="text-caption text-muted-foreground text-center py-2">
                  还有 {{ newRisks.length - 5 }} 条新增风险...
                </p>
              </div>
            </div>

            <div class="space-y-3">
              <h4 class="text-item-title text-[hsl(var(--success))] flex items-center gap-2">
                <SafeIcon name="Minus" :size="16" />
                消失风险点 ({{ disappearedRisks.length }})
              </h4>
              <div class="space-y-2 max-h-96 overflow-y-auto">
                <RiskDiffCard 
                  v-for="risk in disappearedRisks.slice(0, 5)" 
                  :key="risk.id" 
                  :risk="risk" 
                  type="disappeared"
                />
                <p v-if="disappearedRisks.length > 5" class="text-caption text-muted-foreground text-center py-2">
                  还有 {{ disappearedRisks.length - 5 }} 条消失风险...
                </p>
              </div>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="new" class="card-padding space-y-3">
          <div v-if="newRisks.length > 0" class="space-y-3">
            <RiskDiffCard 
              v-for="risk in newRisks" 
              :key="risk.id" 
              :risk="risk" 
              type="new"
            />
          </div>
          <EmptyState 
            v-else
            icon="CheckCircle2"
            title="无新增风险"
            description="任务 2 未发现新的风险点"
          />
        </TabsContent>

        <TabsContent value="disappeared" class="card-padding space-y-3">
          <div v-if="disappearedRisks.length > 0" class="space-y-3">
            <RiskDiffCard 
              v-for="risk in disappearedRisks" 
              :key="risk.id" 
              :risk="risk" 
              type="disappeared"
            />
          </div>
          <EmptyState 
            v-else
            icon="CheckCircle2"
            title="无消失风险"
            description="所有风险点在任务 2 中均已解决"
          />
        </TabsContent>

        <TabsContent value="changed" class="card-padding space-y-3">
          <div v-if="changedRisks.length > 0" class="space-y-3">
            <div v-for="item in changedRisks" :key="item.new.id" class="surface-base p-4 space-y-3">
              <div class="flex items-start justify-between gap-4">
                <div class="flex-1 space-y-2">
                  <h4 class="text-item-title">{{ item.new.title }}</h4>
                  <p class="text-body text-sm">{{ item.new.description }}</p>
                </div>
                <div class="flex items-center gap-2 text-sm font-medium">
                  <span class="text-muted-foreground">{{ item.old.score }}</span>
                  <SafeIcon 
                    :name="item.new.score > item.old.score ? 'ArrowUpRight' : 'ArrowDownRight'" 
                    :size="16"
                    :class="item.new.score > item.old.score ? 'text-destructive' : 'text-[hsl(var(--success))]'"
                  />
                  <span :class="item.new.score > item.old.score ? 'text-destructive' : 'text-[hsl(var(--success))]'">
                    {{ item.new.score }}
                  </span>
                </div>
              </div>
              <p class="text-caption text-muted-foreground">
                {{ item.new.evidenceSummary }}
              </p>
            </div>
          </div>
          <EmptyState 
            v-else
            icon="CheckCircle2"
            title="无变化风险"
            description="所有风险点的评分保持稳定"
          />
        </TabsContent>
      </Tabs>

      <div class="border-t border-border px-6 py-4 flex items-center justify-between">
        <p class="text-caption text-muted-foreground">
          对比生成于 {{ new Date().toLocaleString('zh-CN') }}
        </p>
        <Button @click="handleExport" class="gap-2">
          <SafeIcon name="Download" :size="16" />
          导出对比报告
        </Button>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else-if="selectedTaskIds && totalChanges === 0" class="surface-base card-padding">
      <EmptyState 
        icon="CheckCircle2"
        title="两次任务结果一致"
        description="未发现新增、消失或变化的风险点，系统运行状态稳定"
      />
    </div>

    <!-- No Tasks Selected -->
    <div v-else class="surface-base card-padding">
      <EmptyState 
        icon="AlertCircle"
        title="无法进行对比"
        description="需要至少两个成功完成的任务才能进行差分对比"
        actionLabel="返回历史列表"
        actionHref="./history.html"
      />
    </div>
  </div>

  <div v-else class="page-body flex items-center justify-center h-96">
    <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
  </div>
</template>

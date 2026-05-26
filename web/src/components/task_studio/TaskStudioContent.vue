
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import * as TaskService from '@/data/TaskService'
import * as TaskTemplateService from '@/data/TaskTemplateService'
import * as ZoneService from '@/data/ZoneService'
import type { TaskData } from '@/data/TaskData'
import type { TaskTemplateData } from '@/data/TaskTemplateData'
import type { ZoneData } from '@/data/ZoneData'
import PageHeader from '@/components/common/PageHeader.vue'
import TaskInputSection from './TaskInputSection.vue'
import TaskTemplateList from './TaskTemplateList.vue'
import TaskParameterPanel from './TaskParameterPanel.vue'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

const isClient = ref(true)

const templates = ref<TaskTemplateData[]>(TaskTemplateService.getAll())
const zones = ref<ZoneData[]>(ZoneService.getAll())

const inputText = ref('')
const selectedTemplateId = ref<string>('')
const selectedZoneId = ref<string>(zones.value[0]?.id || '')
const selectedPriority = ref<'low' | 'medium' | 'high'>('medium')
const sampleId = ref<string>('')

const parsePreview = ref<{
  templateName?: string
  zoneName?: string
  priority?: string
  estimatedDuration?: string
} | null>(null)

const isExecuting = ref(false)
const executionProgress = ref(0)

const breadcrumb = [
  { label: '全局总览', href: './dashboard.html' },
  { label: '任务工作坊' }
]

const selectedTemplate = computed(() => {
  return templates.value.find(t => t.id === selectedTemplateId.value)
})

const selectedZone = computed(() => {
  return zones.value.find(z => z.id === selectedZoneId.value)
})

const updateParsePreview = () => {
  if (!inputText.value.trim() && !selectedTemplateId.value) {
    parsePreview.value = null
    return
  }

  parsePreview.value = {
    templateName: selectedTemplate.value?.name || '自定义任务',
    zoneName: selectedZone.value?.name || '未指定',
    priority: selectedPriority.value,
    estimatedDuration: '3-5 分钟'
  }
}

const handleTemplateSelect = (templateId: string) => {
  selectedTemplateId.value = templateId
  const template = templates.value.find(t => t.id === templateId)
  if (template) {
    selectedZoneId.value = template.defaultZoneId
    selectedPriority.value = template.defaultPriority
    inputText.value = `执行${template.name}...`
    updateParsePreview()
  }
}

const handleParameterChange = () => {
  updateParsePreview()
}

const validateForm = (): boolean => {
  if (!inputText.value.trim()) {
    toast.error('请输入任务描述')
    return false
  }
  if (!selectedZoneId.value) {
    toast.error('请选择工作区域')
    return false
  }
  return true
}

const handleExecute = async () => {
  if (!validateForm()) return

  isExecuting.value = true
  executionProgress.value = 0

  try {
    const newTask: TaskData = {
      id: `task-${Date.now()}`,
      name: inputText.value.substring(0, 50),
      inputText: inputText.value,
      templateId: selectedTemplateId.value || 'custom',
      zoneId: selectedZoneId.value,
      sampleId: sampleId.value || undefined,
      priority: selectedPriority.value,
      status: 'queued',
      progress: 0,
      createdAt: new Date().toISOString(),
      createdByUserId: 'user-001',
      updatedAt: new Date().toISOString()
    }

    const allTasks = TaskService.getAll()
    allTasks.push(newTask)
    TaskService.savePersisted(allTasks)

    toast.success('任务已创建，正在启动执行...')

    await new Promise(resolve => setTimeout(resolve, 800))

    window.location.href = `./task-execution-monitor.html?taskId=${newTask.id}`
  } catch (error) {
    toast.error('任务创建失败，请重试')
    isExecuting.value = false
  }
}

const handleReset = () => {
  inputText.value = ''
  selectedTemplateId.value = ''
  selectedZoneId.value = zones.value[0]?.id || ''
  selectedPriority.value = 'medium'
  sampleId.value = ''
  parsePreview.value = null
  toast.info('表单已重置')
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true

    const params = new URLSearchParams(window.location.search)
    const taskId = params.get('taskId')

    if (taskId) {
      const historicalTask = TaskService.getById(taskId)
      if (historicalTask) {
        inputText.value = historicalTask.inputText
        selectedTemplateId.value = historicalTask.templateId
        selectedZoneId.value = historicalTask.zoneId
        selectedPriority.value = historicalTask.priority
        sampleId.value = historicalTask.sampleId || ''
        updateParsePreview()
        toast.success('已加载历史任务参数')
      }
    }
  })
})
</script>

<template>
  <div v-if="isClient" class="flex flex-col min-h-screen bg-background">
    <PageHeader 
      title="任务工作坊"
      subtitle="通过自然语言或预设模板快速创建巡查任务"
      :breadcrumb="breadcrumb"
    >
      <template #actions>
        <Button 
          variant="outline" 
          size="sm"
          @click="handleReset"
          class="gap-2"
        >
          <SafeIcon name="RotateCcw" :size="16" />
          重置表单
        </Button>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0 page-body">
      <div class="max-w-6xl mx-auto space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div class="lg:col-span-2 space-y-6">
            <TaskInputSection 
              v-model="inputText"
              @update:modelValue="updateParsePreview"
            />

            <TaskTemplateList 
              :templates="templates"
              :selected-template-id="selectedTemplateId"
              @select="handleTemplateSelect"
            />
          </div>

          <div class="space-y-6">
            <TaskParameterPanel 
              v-model:zone-id="selectedZoneId"
              v-model:priority="selectedPriority"
              v-model:sample-id="sampleId"
              :zones="zones"
              @change="handleParameterChange"
            />

            <div class="surface-base card-padding space-y-4">
              <h3 class="text-item-title">解析预览</h3>
              
              <div v-if="parsePreview" class="space-y-3 text-sm">
                <div class="flex justify-between items-start">
                  <span class="text-muted-foreground">模板</span>
                  <span class="font-medium text-foreground">{{ parsePreview.templateName }}</span>
                </div>
                <div class="flex justify-between items-start">
                  <span class="text-muted-foreground">区域</span>
                  <span class="font-medium text-foreground">{{ parsePreview.zoneName }}</span>
                </div>
                <div class="flex justify-between items-start">
                  <span class="text-muted-foreground">优先级</span>
                  <span class="font-medium text-foreground capitalize">{{ parsePreview.priority }}</span>
                </div>
                <div class="flex justify-between items-start">
                  <span class="text-muted-foreground">预计耗时</span>
                  <span class="font-medium text-foreground">{{ parsePreview.estimatedDuration }}</span>
                </div>
                <div class="pt-2 border-t border-border/50" />
                <Button 
                  class="w-full gap-2 bg-primary hover:bg-primary-hover text-primary-foreground"
                  :disabled="isExecuting || !inputText.trim()"
                  @click="handleExecute"
                >
                  <SafeIcon v-if="!isExecuting" name="Play" :size="16" />
                  <div v-else class="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  {{ isExecuting ? '启动中...' : '立即执行' }}
                </Button>
              </div>

              <div v-else class="text-center py-8 text-muted-foreground">
                <SafeIcon name="Inbox" :size="32" class="mx-auto mb-2 opacity-30" />
                <p class="text-sm">输入任务或选择模板以生成预览</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

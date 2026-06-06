<!-- 任务工作坊页面：创建自然语言巡检任务，并按 mock/api/hybrid 模式启动执行链路。 -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { getApiErrorDetail, getApiErrorMessage } from '@/api/errors'
import { uploadFile } from '@/api/file-api'
import { buildTaskExecutionSnapshot } from '@/api/mappers'
import { createSceneManifest, preprocessScene } from '@/api/scene-api'
import { executeTask } from '@/api/task-api'
import * as TaskExecutionSnapshotService from '@/data/TaskExecutionSnapshotService'
import * as TaskService from '@/data/TaskService'
import * as TaskTemplateService from '@/data/TaskTemplateService'
import * as ZoneService from '@/data/ZoneService'
import type { TaskData } from '@/data/TaskData'
import type { TaskTemplateData } from '@/data/TaskTemplateData'
import type { ZoneData } from '@/data/ZoneData'
import type { FileAssetType } from '@/lib/api-contracts'
import {
  canFallbackToMock,
  getDefaultDataMode,
  savePersistedDataMode,
  shouldUseApi,
  type DataMode,
} from '@/lib/runtime-mode'
import PageHeader from '@/components/common/PageHeader.vue'
import TaskInputSection from './TaskInputSection.vue'
import TaskTemplateList from './TaskTemplateList.vue'
import TaskParameterPanel from './TaskParameterPanel.vue'
import SceneAssetPanel from './SceneAssetPanel.vue'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

type TaskStatus = TaskData['status']

interface ParsePreview {
  templateName?: string
  zoneName?: string
  priority?: string
  estimatedDuration?: string
  dataMode?: string
  sceneId?: string
}

interface PreparedScene {
  sceneId: string
  sampleId?: string
}

const dataModeLabels: Record<DataMode, string> = {
  mock: 'Mock 演示',
  api: '真实 API',
  hybrid: '混合回退',
}

const isClient = ref(true)
const templates = ref<TaskTemplateData[]>(TaskTemplateService.getAll())
const zones = ref<ZoneData[]>(ZoneService.getAll())

const inputText = ref('')
const selectedTemplateId = ref<string>('')
const selectedZoneId = ref<string>(zones.value[0]?.id || '')
const selectedPriority = ref<'low' | 'medium' | 'high'>('medium')
const sampleId = ref<string>('')

const dataMode = ref<DataMode>(getDefaultDataMode())
const sceneId = ref(buildDefaultSceneId(selectedZoneId.value))
const sceneSampleFileId = ref('')
const imageFile = ref<File | null>(null)
const pointCloudFile = ref<File | null>(null)
const preImageFile = ref<File | null>(null)
const postImageFile = ref<File | null>(null)

const parsePreview = ref<ParsePreview | null>(null)
const isExecuting = ref(false)
const executionProgress = ref(0)
const executionStage = ref('')

const breadcrumb = [
  { label: '全局总览', href: './dashboard.html' },
  { label: '任务工作坊' },
]

// 计算当前选中的任务模板，供参数回填和解析预览使用。
const selectedTemplate = computed(() => {
  return templates.value.find((template) => template.id === selectedTemplateId.value)
})

// 计算当前选中的工作区域，供解析预览和默认 sceneId 使用。
const selectedZone = computed(() => {
  return zones.value.find((zone) => zone.id === selectedZoneId.value)
})

// 生成默认 sceneId，保证真实 API 模式即使不上传资产也有可读的场景标识。
function buildDefaultSceneId(zoneId: string, sample?: string): string {
  const zoneSegment = zoneId || 'scene'
  const sampleSegment = sample && sample !== 'none' ? sample : 'default'
  return `${zoneSegment}-${sampleSegment}`.replace(/[^a-zA-Z0-9_-]/g, '-')
}

// 延迟跳转，保留 toast 和按钮状态的可见反馈。
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

// 读取有效样本 ID，过滤掉下拉框中的 none 占位值。
function getEffectiveSampleId(): string | undefined {
  const value = sampleId.value.trim()
  return value && value !== 'none' ? value : undefined
}

// 在任务参数变化后刷新解析预览。
function updateParsePreview(): void {
  if (!inputText.value.trim() && !selectedTemplateId.value) {
    parsePreview.value = null
    return
  }

  parsePreview.value = {
    templateName: selectedTemplate.value?.name || '自定义任务',
    zoneName: selectedZone.value?.name || '未指定',
    priority: selectedPriority.value,
    estimatedDuration: shouldUseApi(dataMode.value) ? '真实接口返回' : '3-5 分钟',
    dataMode: dataModeLabels[dataMode.value],
    sceneId: sceneId.value.trim() || buildDefaultSceneId(selectedZoneId.value, getEffectiveSampleId()),
  }
}

// 选中模板后回填默认区域、优先级和任务描述。
function handleTemplateSelect(templateId: string): void {
  selectedTemplateId.value = templateId
  const template = templates.value.find((item) => item.id === templateId)

  if (template) {
    selectedZoneId.value = template.defaultZoneId
    selectedPriority.value = template.defaultPriority
    inputText.value = `执行${template.name}...`
    if (!sceneId.value.trim()) {
      sceneId.value = buildDefaultSceneId(template.defaultZoneId, getEffectiveSampleId())
    }
    updateParsePreview()
  }
}

// 参数面板变化后同步默认 sceneId 和解析预览。
function handleParameterChange(): void {
  if (!sceneId.value.trim()) {
    sceneId.value = buildDefaultSceneId(selectedZoneId.value, getEffectiveSampleId())
  }
  updateParsePreview()
}

// 场景资产面板变化后持久化运行模式，并刷新解析预览。
function handleSceneAssetChange(): void {
  savePersistedDataMode(dataMode.value)
  updateParsePreview()
}

// 校验任务表单；真实 API 模式只强制 sceneId，资产可选择已有 manifest、已有样本或现场上传。
function validateForm(): boolean {
  if (!inputText.value.trim()) {
    toast.error('请输入任务描述')
    return false
  }

  if (!selectedZoneId.value) {
    toast.error('请选择工作区域')
    return false
  }

  if (shouldUseApi(dataMode.value) && !sceneId.value.trim()) {
    toast.error('真实 API 模式需要填写 Scene ID')
    return false
  }

  if (shouldUseApi(dataMode.value) && (imageFile.value || pointCloudFile.value) && (!imageFile.value || !pointCloudFile.value)) {
    toast.error('上传预处理需要同时选择正射影像和点云文件')
    return false
  }

  return true
}

// 创建本地任务对象，真实 API 和 mock 执行都会先落本地任务。
function createLocalTask(status: TaskStatus, progress: number): TaskData {
  const now = new Date().toISOString()

  return {
    id: `task-${Date.now()}`,
    name: inputText.value.trim().substring(0, 50) || '自定义巡检任务',
    inputText: inputText.value.trim(),
    templateId: selectedTemplateId.value || 'custom',
    zoneId: selectedZoneId.value,
    sampleId: getEffectiveSampleId(),
    priority: selectedPriority.value,
    status,
    progress,
    createdAt: now,
    startedAt: status === 'running' ? now : undefined,
    createdByUserId: 'user-001',
    updatedAt: now,
  }
}

// 持久化单个任务；存在同 ID 时覆盖，不存在时插入到任务列表顶部。
function persistLocalTask(task: TaskData): void {
  const allTasks = [...TaskService.getAll()]
  const index = allTasks.findIndex((item) => item.id === task.id)

  if (index >= 0) {
    allTasks[index] = task
  } else {
    allTasks.unshift(task)
  }

  TaskService.savePersisted(allTasks)
}

// 跳转到任务执行监控页，统一保留 taskId 查询参数。
function redirectToMonitor(taskId: string): void {
  window.location.href = `./task-execution-monitor.html?taskId=${taskId}`
}

// 按类型上传场景文件，缺失 fileId 时主动抛错，避免后续预处理拿到空引用。
async function uploadSceneFile(file: File, fileType: FileAssetType): Promise<string> {
  const response = await uploadFile(file, fileType)
  const fileId = response.data?.fileId

  if (!fileId) {
    throw new Error(`文件 ${file.name} 上传成功但未返回 fileId`)
  }

  return fileId
}

// 准备真实 API 执行所需的 scene manifest：优先已有样本，其次上传预处理，最后复用已注册 manifest。
async function prepareSceneAssets(): Promise<PreparedScene> {
  const preparedSceneId = sceneId.value.trim()
  const preparedSampleId = getEffectiveSampleId()
  const preparedSceneSampleFileId = sceneSampleFileId.value.trim()

  if (preparedSceneSampleFileId) {
    executionStage.value = '正在注册场景样本...'
    executionProgress.value = 25
    await createSceneManifest(preparedSceneId, {
      sceneSampleFileId: preparedSceneSampleFileId,
      sampleId: preparedSampleId || preparedSceneId,
    })
    return { sceneId: preparedSceneId, sampleId: preparedSampleId }
  }

  if (imageFile.value && pointCloudFile.value) {
    executionStage.value = '正在上传场景资产...'
    executionProgress.value = 20
    const imageFileId = await uploadSceneFile(imageFile.value, 'image')
    const pointCloudFileId = await uploadSceneFile(pointCloudFile.value, 'point_cloud')
    const preImageFileId = preImageFile.value ? await uploadSceneFile(preImageFile.value, 'image') : undefined
    const postImageFileId = postImageFile.value ? await uploadSceneFile(postImageFile.value, 'image') : undefined

    executionStage.value = '正在预处理场景...'
    executionProgress.value = 45
    const response = await preprocessScene({
      sceneId: preparedSceneId,
      sampleId: preparedSampleId,
      imageFileId,
      pointCloudFileId,
      preImageFileId,
      postImageFileId,
    })

    return {
      sceneId: response.data?.sceneId || preparedSceneId,
      sampleId: response.data?.sampleId || preparedSampleId,
    }
  }

  executionStage.value = '使用已注册场景...'
  executionProgress.value = 20
  return { sceneId: preparedSceneId, sampleId: preparedSampleId }
}

// 把后端执行状态映射成本地任务状态，未知状态默认按错误数量兜底。
function resolveApiTaskStatus(executionStatus: string, errorCount: number): TaskStatus {
  const status = executionStatus.trim().toUpperCase()
  if (status === 'SUCCESS' || status === 'SUCCEEDED' || status === 'COMPLETED' || status === 'DONE') return 'success'
  if (status === 'FAILED' || status === 'ERROR' || status === 'ABSTAINED') return 'failed'
  return errorCount > 0 ? 'failed' : 'success'
}

// 使用真实 API 执行任务，并把响应转换为本地执行快照供后续页面消费。
async function executeApiTask(localTask: TaskData): Promise<TaskData> {
  const preparedScene = await prepareSceneAssets()

  executionStage.value = '正在调用智能体执行...'
  executionProgress.value = 70
  const response = await executeTask({
    taskText: inputText.value.trim(),
    sceneId: preparedScene.sceneId,
    debug: true,
  })

  if (!response.data) {
    throw new Error('任务执行响应缺少 data 字段')
  }

  const snapshot = buildTaskExecutionSnapshot(response.data, localTask.id)
  TaskExecutionSnapshotService.saveSnapshot(snapshot)

  const now = new Date().toISOString()
  const completedTask: TaskData = {
    ...localTask,
    sampleId: preparedScene.sampleId ?? localTask.sampleId,
    status: resolveApiTaskStatus(snapshot.executionStatus, snapshot.errorCount),
    progress: 100,
    finishedAt: now,
    updatedAt: now,
  }

  persistLocalTask(completedTask)
  executionProgress.value = 100
  executionStage.value = '执行完成'
  return completedTask
}

// 将任务标记为失败，保留已创建的本地任务方便后续排查。
function markTaskFailed(task: TaskData): TaskData {
  const now = new Date().toISOString()
  return {
    ...task,
    status: 'failed',
    progress: 100,
    finishedAt: now,
    updatedAt: now,
  }
}

// 启动 mock 演示任务；混合模式回退时会复用已经创建的任务 ID。
async function startMockTask(existingTask?: TaskData): Promise<void> {
  const now = new Date().toISOString()
  const task = existingTask
    ? {
        ...existingTask,
        status: 'running' as TaskStatus,
        progress: 5,
        startedAt: existingTask.startedAt || now,
        finishedAt: undefined,
        updatedAt: now,
      }
    : createLocalTask('running', 5)

  executionStage.value = '正在启动本地演示任务...'
  executionProgress.value = 10
  persistLocalTask(task)
  toast.success('任务已创建，正在启动执行...')

  await delay(800)
  redirectToMonitor(task.id)
}

// 处理立即执行按钮：按当前运行模式选择 mock、本地 API 或混合回退链路。
async function handleExecute(): Promise<void> {
  if (!validateForm()) return

  isExecuting.value = true
  executionProgress.value = 0
  executionStage.value = '正在创建任务...'
  savePersistedDataMode(dataMode.value)

  if (!shouldUseApi(dataMode.value)) {
    await startMockTask()
    return
  }

  const runningTask = createLocalTask('running', 10)
  persistLocalTask(runningTask)

  try {
    toast.info('任务已创建，正在连接真实 API...')
    const completedTask = await executeApiTask(runningTask)
    toast.success(completedTask.status === 'success' ? '真实 API 执行完成' : '真实 API 执行结束，存在失败或需复核状态')
    await delay(300)
    redirectToMonitor(completedTask.id)
  } catch (error) {
    console.error('任务 API 执行失败', getApiErrorDetail(error))

    if (canFallbackToMock(dataMode.value)) {
      toast.warning(`真实 API 执行失败，已回退到 mock 演示：${getApiErrorMessage(error)}`)
      await startMockTask(runningTask)
      return
    }

    const failedTask = markTaskFailed(runningTask)
    persistLocalTask(failedTask)
    toast.error(getApiErrorMessage(error))
    isExecuting.value = false
    executionStage.value = ''
  }
}

// 重置任务表单和场景资产，保留用户选择的运行模式。
function handleReset(): void {
  inputText.value = ''
  selectedTemplateId.value = ''
  selectedZoneId.value = zones.value[0]?.id || ''
  selectedPriority.value = 'medium'
  sampleId.value = ''
  sceneId.value = buildDefaultSceneId(selectedZoneId.value)
  sceneSampleFileId.value = ''
  imageFile.value = null
  pointCloudFile.value = null
  preImageFile.value = null
  postImageFile.value = null
  parsePreview.value = null
  toast.info('表单已重置')
}

// 组件挂载后恢复历史任务参数，支持从监控页或历史页回到工作坊继续调整。
onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true

    const params = new URLSearchParams(window.location.search)
    const taskId = params.get('taskId')

    if (!taskId) return

    const historicalTask = TaskService.getById(taskId)
    if (!historicalTask) return

    inputText.value = historicalTask.inputText
    selectedTemplateId.value = historicalTask.templateId
    selectedZoneId.value = historicalTask.zoneId
    selectedPriority.value = historicalTask.priority
    sampleId.value = historicalTask.sampleId || ''
    sceneId.value = buildDefaultSceneId(historicalTask.zoneId, historicalTask.sampleId)
    updateParsePreview()
    toast.success('已加载历史任务参数')
  })
})
</script>

<template>
  <div v-if="isClient" class="flex flex-col min-h-screen bg-background">
    <PageHeader
      title="任务工作坊"
      subtitle="通过自然语言或预设模板创建巡检任务"
      :breadcrumb="breadcrumb"
    >
      <template #actions>
        <Button
          variant="outline"
          size="sm"
          class="gap-2"
          :disabled="isExecuting"
          @click="handleReset"
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

            <SceneAssetPanel
              v-model:data-mode="dataMode"
              v-model:scene-id="sceneId"
              v-model:scene-sample-file-id="sceneSampleFileId"
              v-model:image-file="imageFile"
              v-model:point-cloud-file="pointCloudFile"
              v-model:pre-image-file="preImageFile"
              v-model:post-image-file="postImageFile"
              :disabled="isExecuting"
              @change="handleSceneAssetChange"
            />

            <div class="surface-base card-padding space-y-4">
              <h3 class="text-item-title">解析预览</h3>

              <div v-if="parsePreview" class="space-y-3 text-sm">
                <div class="flex justify-between items-start gap-4">
                  <span class="text-muted-foreground">模板</span>
                  <span class="font-medium text-foreground text-right">{{ parsePreview.templateName }}</span>
                </div>
                <div class="flex justify-between items-start gap-4">
                  <span class="text-muted-foreground">区域</span>
                  <span class="font-medium text-foreground text-right">{{ parsePreview.zoneName }}</span>
                </div>
                <div class="flex justify-between items-start gap-4">
                  <span class="text-muted-foreground">优先级</span>
                  <span class="font-medium text-foreground capitalize">{{ parsePreview.priority }}</span>
                </div>
                <div class="flex justify-between items-start gap-4">
                  <span class="text-muted-foreground">运行模式</span>
                  <span class="font-medium text-foreground">{{ parsePreview.dataMode }}</span>
                </div>
                <div class="flex justify-between items-start gap-4">
                  <span class="text-muted-foreground">Scene ID</span>
                  <span class="font-medium text-foreground text-right break-all">{{ parsePreview.sceneId }}</span>
                </div>
                <div class="flex justify-between items-start gap-4">
                  <span class="text-muted-foreground">预计耗时</span>
                  <span class="font-medium text-foreground">{{ parsePreview.estimatedDuration }}</span>
                </div>
                <div class="pt-2 border-t border-border/50" />
                <div v-if="isExecuting" class="space-y-2">
                  <div class="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div class="h-full rounded-full bg-primary transition-all" :style="{ width: `${executionProgress}%` }" />
                  </div>
                  <p class="text-xs text-muted-foreground">{{ executionStage }}</p>
                </div>
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

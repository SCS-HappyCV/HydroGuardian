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
import RealSpatialMap, { type SpatialMapBounds, type SpatialMapMarker } from '@/components/common/RealSpatialMap.vue'
import TaskInputSection from './TaskInputSection.vue'
import TaskParameterPanel from './TaskParameterPanel.vue'
import SceneAssetPanel from './SceneAssetPanel.vue'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { competitionDemo } from '@/data/CompetitionDemoData'
import { agentDemoScenarios, getAgentDemoScenario } from '@/data/agent-demo/scenarios'
import { matchAgentDemoScenario } from '@/lib/agent-scenario-matcher'
import { localAgentRuntime } from '@/lib/local-agent-runtime'
import { remoteAgentApi } from '@/api/remote-agent-api'
import { remoteAgentProvider } from '@/lib/remote-agent-provider'
import type { AgentDemoScenario, AgentPresentationSnapshot, AgentResponseOption } from '@/lib/agent-presentation-types'
import AgentPlanActionBar from './AgentPlanActionBar.vue'
import { spatialMetadataForUpload } from '@/lib/spatial-metadata'

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
  mock: '预置场景',
  api: '实时分析',
  hybrid: '自动保障',
}

const templateTaskPrompts: Record<string, string> = {
  'tpl-001': '找出靠近水线的细长沟渠，并排除道路，按风险高低排序',
  'tpl-002': '找出高于水线的陡坡裸地区域，并按坡度和临水距离排序',
  'tpl-003': '筛查近水扰动区域，结合前后影像变化按风险高低排序',
  'tpl-004': '综合筛查岸线附近沟渠、陡坡裸地与新增扰动，输出证据和处置建议',
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
const isGoldenCase = ref(false)
const selectedAgentScenarioId = ref('')
const agentResult = ref<AgentPresentationSnapshot | null>(null)
const showSceneSettings = ref(false)
const sceneMapExpanded = ref(false)
const sceneSpatialPreview = computed(() => {
  const source = postImageFile.value || imageFile.value || pointCloudFile.value || preImageFile.value
  if (!source) return undefined
  const role = source === pointCloudFile.value ? 'point_cloud_path' : source === preImageFile.value ? 'before_image_path' : source === postImageFile.value ? 'after_image_path' : 'image_path'
  const metadata = spatialMetadataForUpload(source, role) as { extent?: { geographic?: { west: number; south: number; east: number; north: number; center_lon: number; center_lat: number } }; crs?: { code?: number; name?: string } } | undefined
  const geographic = metadata?.extent?.geographic
  if (!geographic) return undefined
  const bounds: SpatialMapBounds = { west: geographic.west, south: geographic.south, east: geographic.east, north: geographic.north }
  const marker: SpatialMapMarker = { id: 'scene-center', title: '巡查场景中心', longitude: geographic.center_lon, latitude: geographic.center_lat, level: 'target', subtitle: source.name }
  return { bounds, marker, epsg: metadata?.crs?.code, crsName: metadata?.crs?.name, fileName: source.name }
})

const breadcrumb = [
  { label: '智巡总览', href: './dashboard.html' },
  { label: '发起巡查' },
]

// 计算当前选中的任务模板，供参数回填和解析预览使用。
const selectedTemplate = computed(() => {
  return templates.value.find((template) => template.id === selectedTemplateId.value)
})

// 计算当前选中的工作区域，供解析预览和默认 sceneId 使用。
const selectedZone = computed(() => {
  return zones.value.find((zone) => zone.id === selectedZoneId.value)
})

const matchedAgentScenario = computed<AgentDemoScenario | null>(() => {
  if (!inputText.value.trim()) return null
  return getAgentDemoScenario(selectedAgentScenarioId.value)
    ?? matchAgentDemoScenario({ taskText: inputText.value, sceneId: sceneId.value })
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

function handleTaskTextChange(value: string): void {
  inputText.value = value
  const selectedScenario = getAgentDemoScenario(selectedAgentScenarioId.value)
  if (selectedScenario && selectedScenario.taskText !== value.trim()) {
    selectedAgentScenarioId.value = ''
  }
  agentResult.value = null
  showSceneSettings.value = false
  updateParsePreview()
}

function handleAgentScenarioSelect(scenario: AgentDemoScenario): void {
  const scenarioTask = scenario.timeline[0].snapshot.task
  selectedAgentScenarioId.value = scenario.scenarioId
  inputText.value = scenario.taskText
  selectedTemplateId.value = ''
  sceneId.value = scenarioTask.sceneId || buildDefaultSceneId(selectedZoneId.value)
  sampleId.value = scenarioTask.sampleId || ''
  selectedPriority.value = scenario.decisionType === 'workflow' || scenario.decisionType === 'abstain' ? 'high' : 'medium'
  dataMode.value = 'mock'
  savePersistedDataMode('mock')
  agentResult.value = null
  updateParsePreview()
}

function handleAgentResponseOption(option: AgentResponseOption): void {
  if (option.optionId === 'scope-standard') {
    sceneId.value = 'scene-riverbank-001'
    toast.success('已选择当前预置场景，请继续明确巡查重点')
    updateParsePreview()
    return
  }

  const workflowScenario = getAgentDemoScenario('near-water-disturbance-workflow')
  if (!workflowScenario) return
  handleAgentScenarioSelect(workflowScenario)
  toast.success(option.optionId === 'target-disturbance' ? '已切换为新增扰动筛查任务' : '已切换为综合筛查任务')
}

// 选中模板后回填默认区域、优先级和任务描述。
function handleTemplateSelect(templateId: string): void {
  selectedAgentScenarioId.value = ''
  agentResult.value = null
  selectedTemplateId.value = templateId
  const template = templates.value.find((item) => item.id === templateId)

  if (template) {
    selectedZoneId.value = template.defaultZoneId
    selectedPriority.value = template.defaultPriority
    inputText.value = templateTaskPrompts[template.id] || template.description
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

  if (Boolean(preImageFile.value) !== Boolean(postImageFile.value)) {
    toast.error('进行变化分析时，请同时上传前、后时相影像')
    return false
  }

  if (!shouldUseApi(dataMode.value) && !matchedAgentScenario.value) {
    toast.error('预置场景需要选择一个任务目标')
    return false
  }

  return true
}

// 创建本地任务对象，真实 API 和 mock 执行都会先落本地任务。
function createLocalTask(status: TaskStatus, progress: number, taskId?: string): TaskData {
  const now = new Date().toISOString()

  return {
    id: taskId || `task-${Date.now()}`,
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

function getLocalAssetRoles(scenario: AgentDemoScenario): string[] {
  const roles = new Set(scenario.timeline[0].snapshot.task.availableAssets)
  if (imageFile.value) roles.add('正射影像')
  if (pointCloudFile.value) roles.add('点云')
  if (preImageFile.value) roles.add('前时相影像')
  if (postImageFile.value) roles.add('后时相影像')
  return [...roles]
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

// 启动预置场景任务；典型案例会复用固定 ID，保证风险和工单关联不丢失。
async function startLocalAgentTask(taskId?: string): Promise<void> {
  const scenario = matchedAgentScenario.value
  if (!scenario) return

  executionStage.value = '正在生成 Agent 决策...'
  executionProgress.value = 20
  const initialSnapshot = await localAgentRuntime.createTask({
    taskId,
    taskText: inputText.value.trim(),
    sceneId: sceneId.value.trim() || scenario.timeline[0].snapshot.task.sceneId,
    sampleId: getEffectiveSampleId(),
    assetRoles: getLocalAssetRoles(scenario),
    scenarioId: scenario.scenarioId,
  })

  const shouldEnterExecution = scenario.decisionType === 'workflow' || scenario.decisionType === 'tool_call'
  const task = createLocalTask(shouldEnterExecution ? 'running' : 'success', shouldEnterExecution ? 5 : 100, initialSnapshot.task.taskId)
  persistLocalTask(task)

  if (shouldEnterExecution) {
    localAgentRuntime.start(task.id)
    executionStage.value = scenario.decisionType === 'workflow' ? '正在组织专家协同流程...' : '正在调用专家能力...'
    executionProgress.value = 35
    toast.success('Agent 决策完成，正在进入智能执行')
    await delay(500)
    redirectToMonitor(task.id)
    return
  }

  agentResult.value = localAgentRuntime.complete(task.id) ?? initialSnapshot
  executionProgress.value = 100
  executionStage.value = 'Agent 决策完成'
  isExecuting.value = false
  window.history.replaceState(null, '', `./task-studio.html?taskId=${task.id}`)

  if (scenario.decisionType === 'clarification') toast.info('请根据 Agent 建议补充任务信息')
  else if (scenario.decisionType === 'abstain') toast.warning('当前条件不足，系统未强行生成风险结论')
  else toast.success('Agent 已形成场景回答')
}

async function uploadRemoteAsset(file: File, role: string): Promise<string> {
  executionStage.value = `正在上传${role}...`
  const presigned = await remoteAgentApi.presignUpload({ filename: file.name, media_type: file.type || 'application/octet-stream', job_id: 'uploads' })
  await remoteAgentApi.uploadFile(presigned.upload_url, file)
  const spatial = spatialMetadataForUpload(file, role)
  await remoteAgentApi.completeUpload(presigned.artifact.artifact_id, { original_name: file.name, role, ...(spatial ? { spatial } : {}) })
  return presigned.artifact_uri
}

async function startRemoteAgentTask(task: TaskData): Promise<void> {
  const assets: Record<string, string> = {}
  const uploadItems: Array<[File | null, string, string]> = [
    [imageFile.value, 'image_path', '正射影像'],
    [pointCloudFile.value, 'point_cloud_path', '点云'],
    [preImageFile.value, 'before_image_path', '前时相影像'],
    [postImageFile.value, 'after_image_path', '后时相影像'],
  ]
  for (const [file, key, label] of uploadItems) if (file) assets[key] = await uploadRemoteAsset(file, label)
  executionStage.value = '正在提交任务并生成执行计划...'
  executionProgress.value = 45
  await remoteAgentProvider.createTask({
    taskId: task.id,
    taskText: task.inputText,
    sceneId: sceneId.value,
    assets,
    metadata: {
      name: task.name,
      template_id: task.templateId,
      zone_id: task.zoneId,
      sample_id: task.sampleId,
      priority: task.priority,
      created_by_user_id: task.createdByUserId,
      metadata: { source: 'web-task-studio', asset_roles: Object.keys(assets) },
    },
  })
  executionProgress.value = 60
  toast.success('任务已提交至真实 Agent，正在调度专家')
  await delay(300)
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
    await startLocalAgentTask()
    return
  }

  const runningTask = createLocalTask('running', 10)
  persistLocalTask(runningTask)

  try {
    toast.info('任务已创建，正在连接真实 Agent...')
    await startRemoteAgentTask(runningTask)
  } catch (error) {
    console.error('任务 API 执行失败', getApiErrorDetail(error))

    if (canFallbackToMock(dataMode.value) && matchedAgentScenario.value) {
      toast.warning(`实时服务暂不可用，已启用保障数据：${getApiErrorMessage(error)}`)
      await startLocalAgentTask(runningTask.id)
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
  selectedAgentScenarioId.value = ''
  agentResult.value = null
  toast.info('表单已重置')
}

// 组件挂载后恢复历史任务参数，支持从监控页或历史页回到工作坊继续调整。
onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true

    const params = new URLSearchParams(window.location.search)
    const taskId = params.get('taskId')
    const requestedSceneId = params.get('sceneId')
    isGoldenCase.value = params.get('demo') === 'golden-case' || taskId === competitionDemo.taskId

    if (isGoldenCase.value) {
      dataMode.value = 'mock'
      savePersistedDataMode('mock')
      selectedAgentScenarioId.value = 'near-water-disturbance-workflow'
    }

    if (!taskId) return

    const historicalTask = TaskService.getById(taskId)
    if (!historicalTask) return

    const localSession = localAgentRuntime.getSession(taskId)
    if (localSession) {
      selectedAgentScenarioId.value = localSession.scenarioId
      const storedSnapshot = localAgentRuntime.getSnapshot(taskId)
      if (storedSnapshot?.response) agentResult.value = storedSnapshot
    }

    inputText.value = historicalTask.inputText
    selectedTemplateId.value = historicalTask.templateId
    selectedZoneId.value = historicalTask.zoneId
    selectedPriority.value = historicalTask.priority
    sampleId.value = historicalTask.sampleId || ''
    sceneId.value = requestedSceneId || buildDefaultSceneId(historicalTask.zoneId, historicalTask.sampleId)
    updateParsePreview()
    toast.success('已加载历史任务参数')
  })
})
</script>

<template>
  <div v-if="isClient" class="flex min-h-screen flex-col bg-background">
    <PageHeader
      title="发起智能巡查"
      subtitle="描述目标、上传数据，其余交给 Agent"
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
          清空
        </Button>
      </template>
    </PageHeader>

    <div class="min-h-0 flex-1 overflow-y-auto page-body">
      <div class="mx-auto max-w-[1180px] space-y-4 pb-8">
        <div class="grid items-start gap-4 lg:grid-cols-[minmax(0,.9fr)_minmax(0,1.1fr)]">
          <TaskInputSection :model-value="inputText" @update:model-value="handleTaskTextChange" />
          <SceneAssetPanel v-model:data-mode="dataMode" v-model:scene-id="sceneId" v-model:scene-sample-file-id="sceneSampleFileId" v-model:image-file="imageFile" v-model:point-cloud-file="pointCloudFile" v-model:pre-image-file="preImageFile" v-model:post-image-file="postImageFile" :disabled="isExecuting" @change="handleSceneAssetChange" />
        </div>

        <section v-if="sceneSpatialPreview" class="mx-auto w-full max-w-[820px] overflow-hidden rounded-2xl border border-cyan-300/15 bg-[#07131d]/80 p-3">
          <div class="mb-3 flex flex-wrap items-center justify-between gap-2 px-1">
            <div class="flex items-center gap-2">
              <span class="grid h-8 w-8 place-items-center rounded-lg bg-cyan-300/10 text-cyan-200"><SafeIcon name="MapPinned" :size="15" /></span>
              <div><p class="text-xs font-semibold text-white">任务空间范围已识别</p><p class="mt-0.5 max-w-[540px] truncate text-[10px] text-slate-400">{{ sceneSpatialPreview.fileName }}</p></div>
            </div>
            <div class="flex items-center gap-2">
              <span class="hidden rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2.5 py-1 text-[9px] text-emerald-200 sm:inline-flex">EPSG:{{ sceneSpatialPreview.epsg }} · 提交后随任务传递</span>
              <button type="button" class="inline-flex h-7 items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 text-[10px] text-slate-300 transition hover:border-cyan-300/20 hover:text-cyan-100" @click="sceneMapExpanded = !sceneMapExpanded">
                <SafeIcon :name="sceneMapExpanded ? 'Minimize2' : 'Maximize2'" :size="12" />{{ sceneMapExpanded ? '收起地图' : '展开地图' }}
              </button>
            </div>
          </div>
          <div class="mx-auto max-w-[760px]">
            <RealSpatialMap :center="sceneSpatialPreview.marker" :bounds="sceneSpatialPreview.bounds" :markers="[sceneSpatialPreview.marker]" :height="sceneMapExpanded ? 'clamp(300px, 32vw, 380px)' : '220px'" compact />
          </div>
        </section>

        <details class="rounded-2xl border border-white/[0.07] bg-card/40 px-4 py-3">
          <summary class="cursor-pointer text-xs font-medium text-muted-foreground">更多设置与任务模板</summary>
          <div class="mt-4 grid items-start gap-4 lg:grid-cols-[minmax(280px,.38fr)_minmax(0,.62fr)]">
            <TaskParameterPanel v-model:zone-id="selectedZoneId" v-model:priority="selectedPriority" v-model:sample-id="sampleId" :zones="zones" @change="handleParameterChange" />
            <div>
              <p class="mb-2 text-xs text-muted-foreground">快速填入任务目标</p>
              <div class="grid gap-2 sm:grid-cols-2">
                <button v-for="scenario in agentDemoScenarios" :key="scenario.scenarioId" type="button" class="rounded-xl border px-3 py-2.5 text-left text-xs transition disabled:opacity-50" :class="scenario.scenarioId === matchedAgentScenario?.scenarioId ? 'border-primary/40 bg-primary/[0.08] text-primary' : 'border-white/[0.07] bg-black/10 text-card-foreground hover:border-white/[0.14]'" :disabled="isExecuting" @click="handleAgentScenarioSelect(scenario)">
                  <strong class="block truncate font-medium">{{ scenario.title }}</strong><span class="mt-1 block truncate text-[10px] text-muted-foreground">{{ scenario.taskText }}</span>
                </button>
              </div>
            </div>
          </div>
        </details>

        <AgentPlanActionBar :disabled="!inputText.trim() || !selectedZoneId" :is-executing="isExecuting" :progress="executionProgress" :stage="executionStage" @execute="handleExecute" />
      </div>
    </div>
  </div>
</template>

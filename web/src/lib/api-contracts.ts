// HydroGuardian 前端 API 契约：集中维护网关路径、统一响应外壳和核心 DTO 类型。

export const DEFAULT_API_BASE_URL = 'http://localhost:8080'
export const API_VERSION_PREFIX = '/api/v1'
export const API_SUCCESS_CODE = '0'

export const API_ERROR_CODES = {
  badRequest: '40000',
  unauthorized: '40100',
  forbidden: '40300',
  notFound: '40400',
  conflict: '40900',
  validationFailed: '42200',
  internalError: '50000',
  upstreamUnavailable: '50200',
} as const

export const API_PATHS = {
  auth: {
    login: `${API_VERSION_PREFIX}/auth/login`,
    register: `${API_VERSION_PREFIX}/auth/register`,
    refresh: `${API_VERSION_PREFIX}/auth/refresh`,
    logout: `${API_VERSION_PREFIX}/auth/logout`,
    me: `${API_VERSION_PREFIX}/auth/me`,
    changePassword: `${API_VERSION_PREFIX}/auth/change-password`,
  },
  files: {
    upload: `${API_VERSION_PREFIX}/files`,
    // 按 fileId 查询文件元数据。
    detail: (fileId: string) => `${API_VERSION_PREFIX}/files/${encodeURIComponent(fileId)}`,
  },
  scenes: {
    preprocess: `${API_VERSION_PREFIX}/scenes/preprocess`,
    // 按 sceneId 注册或查询场景资产清单。
    manifest: (sceneId: string) => `${API_VERSION_PREFIX}/scenes/${encodeURIComponent(sceneId)}/manifest`,
  },
  tasks: {
    execute: `${API_VERSION_PREFIX}/tasks/execute`,
  },
  workOrders: {
    // 按工单 ID 查询单个工单详情。
    detail: (workOrderId: string) => `${API_VERSION_PREFIX}/work-orders/${encodeURIComponent(workOrderId)}`,
    // 更新工单状态。
    status: (workOrderId: string) => `${API_VERSION_PREFIX}/work-orders/${encodeURIComponent(workOrderId)}/status`,
  },
  cases: {
    // 查询指定 case 下的工单列表。
    workOrders: (caseId: string) => `${API_VERSION_PREFIX}/cases/${encodeURIComponent(caseId)}/work-orders`,
    // 预留完整智能体快照接口；当前后端若未实现，调用方需要自行兜底。
    agentResult: (caseId: string) => `${API_VERSION_PREFIX}/cases/${encodeURIComponent(caseId)}/agent-result`,
  },
} as const

export type ApiErrorCode = (typeof API_ERROR_CODES)[keyof typeof API_ERROR_CODES]
export type ApiCode = typeof API_SUCCESS_CODE | ApiErrorCode | (string & {})
export type ApiQueryValue = string | number | boolean | null | undefined
export type ApiQuery = Record<string, ApiQueryValue | ApiQueryValue[]>

export interface ApiResponse<T = unknown> {
  code: ApiCode
  message: string
  traceId: string
  data?: T
}

export interface ApiPageRequest {
  page?: number
  pageSize?: number
}

export interface ApiPageResponse<T> {
  records: T[]
  total: number
  page: number
  pageSize: number
}

export interface AuthUser {
  id: string
  name: string
  email: string
  role?: string
  department?: string
  avatarUrl?: string
}

export interface LoginRequest {
  email: string
  password: string
  rememberMe?: boolean
}

export interface LoginResponseData {
  token: string
  tokenType?: string
  expiresIn?: number
  user?: AuthUser
}

export interface RegisterRequest {
  name: string
  email: string
  password: string
  confirmPassword: string
  agreeTerms: boolean
}

export interface RegisterResponseData {
  userId?: string
  email?: string
  createdAt?: string
}

export type FileAssetType = 'image' | 'point_cloud' | 'scene_sample' | 'evidence' | 'generic' | (string & {})

export interface FileAssetData {
  fileId: string
  fileName: string
  contentType: string
  size: number
  downloadUrl: string
  objectKey: string
  fileType: FileAssetType
  checksumSha256: string
}

export interface ScenePreprocessRequestData {
  sceneId: string
  sampleId?: string
  imageFileId: string
  pointCloudFileId: string
  preImageFileId?: string
  postImageFileId?: string
  preprocessVersion?: string
  imageSize?: number
  maxPoints?: number
}

export interface ScenePreprocessResponseData {
  sceneId: string
  sampleId: string
  sceneSampleFileId: string
  imageFileId: string
  pointCloudFileId: string
  preImageFileId: string
  postImageFileId: string
  preprocessVersion: string
  manifestRegistered: boolean
  checksumSha256: string
  sceneSampleFileName: string
  status: string
  qualityReport: Record<string, unknown> | string
}

export interface SceneManifestRequestData {
  sceneSampleFileId: string
  sampleId?: string
  imageFileId?: string
  pointCloudFileId?: string
  preImageFileId?: string
  postImageFileId?: string
  preprocessVersion?: string
  checksumSha256?: string
  schemaVersion?: string
}

export interface SceneManifestData {
  sceneId: string
  sampleId: string
  sceneSampleFileId: string
  imageFileId: string
  pointCloudFileId: string
  preImageFileId: string
  postImageFileId: string
  preprocessVersion: string
  checksumSha256: string
  schemaVersion: string
  createdAt: string
  updatedAt: string
}

export interface AgentTraceItem {
  stage: string
  message: string
  dataJson?: string
}

export interface AgentErrorItem {
  stage: string
  message: string
  dataJson?: string
}

export interface ExecuteTaskRequestData {
  taskText: string
  sceneId: string
  debug?: boolean
}

export interface ExecuteTaskResponseData {
  task: {
    taskText: string
    sceneId: string
  }
  parsed: {
    targetType: string
    parserSource: string
  }
  risk: {
    score: number
    riskLevel: string
    reviewRequired: boolean
  }
  recommendation: {
    action: string
  }
  workOrders: unknown
  case: {
    caseId: string
    status: string
    persistenceStatus: string
    persistenceError: string
  }
  execution: {
    status: string
    evidenceStatus: string
    traceCount: number
    errorCount: number
  }
  errors?: AgentErrorItem[]
  trace?: AgentTraceItem[]
}

export interface TaskExecutionSnapshot {
  localTaskId: string
  taskText: string
  sceneId: string
  targetType: string
  parserSource: string
  evidenceStatus: string
  riskScore: number
  riskLevel: string
  reviewRequired: boolean
  recommendationAction: string
  caseId: string
  caseStatus: string
  executionStatus: string
  traceTotal: number
  errorCount: number
  trace: AgentTraceItem[]
  errors: AgentErrorItem[]
  casePersistenceStatus: string
  casePersistenceError: string
  createdAt: string
}

export interface WorkOrderData {
  workOrderId: string
  caseId: string
  riskCardId: string
  riskType: string
  riskLevel: string
  title: string
  summary: string
  recommendedAction: string
  status: string
  assignee: string
  deadline: string
  closureNote: string
  evidenceSummary: unknown
  schemaVersion: string
  createdAt: string
  updatedAt: string
}

export interface ListCaseWorkOrdersResponseData {
  workOrders: WorkOrderData[]
}

export interface UpdateWorkOrderStatusRequestData {
  status: string
  assignee?: string
  closureNote?: string
}

export interface AgentResultCaseData {
  caseId: string
  title: string
  taskText: string
  sceneId: string
  status: string
  riskLevel: string
  assignee: string
  tags: unknown
  createdAt: string
}

export interface AgentVisualizationBBoxPixelData {
  x: number
  y: number
  width: number
  height: number
}

export interface AgentVisualizationPointData {
  x: number
  y: number
}

export interface AgentVisualizationOrthoData {
  schemaVersion?: string
  sourceFile?: Partial<FileAssetData>
  originalWidth?: number
  originalHeight?: number
  displayWidth?: number
  displayHeight?: number
  coordinateMode?: string
  projectionStatus?: string
  projectionWarning?: string
}

export interface AgentRiskOverlayData {
  overlayId?: string
  regionId?: string
  label?: string
  riskCardId?: string
  riskType?: string
  riskLevel?: string
  riskScore?: number
  reviewRequired?: boolean
  candidateScore?: number
  support?: number
  pointCount?: number
  bboxPixel?: AgentVisualizationBBoxPixelData
  polygonPixel?: AgentVisualizationPointData[]
  bbox3d?: unknown
  centroid?: number[]
  summary?: string
  color?: string
  projectionMode?: string
  projectionConfidence?: string
}

export interface AgentEvidenceMetricsData {
  schemaVersion?: string
  status?: string
  targetHit?: boolean
  decisionKind?: string
  reviewRequired?: boolean
  confidence?: number
  confidenceComponents?: Record<string, number>
  selectedCandidateIdx?: number | null
  selectedCandidateScore?: number
  selectedCandidatePosterior?: number
  selectedCandidateIsNoTarget?: boolean
  selectedVerifierScore?: number
  posteriorNoTargetMass?: number
  abstainProbability?: number
  selectedMaskMass?: number
  selectedMaskPeak?: number
  maskSelectionMode?: string
  candidateRegionCount?: number
  evidenceSummary?: string[]
}

export interface AgentChangeComparisonData {
  schemaVersion?: string
  status?: string
  changeType?: string
  changeScore?: number | null
  changeSummary?: string
  reviewRequired?: boolean
  preImage?: Partial<FileAssetData>
  postImage?: Partial<FileAssetData>
  changeMask?: Partial<FileAssetData>
  canCompare?: boolean
  maskAvailable?: boolean
  alignmentStatus?: string
}

export interface AgentPointCloudVisualizationData {
  schemaVersion?: string
  sourceFile?: Partial<FileAssetData>
  sceneSampleFile?: Partial<FileAssetData>
  coordinateMode?: string
  pointCountOriginal?: number
  pointCountSampled?: number
  hasRgb?: boolean
  geometryFeatureNames?: string[]
  geometryCellSize?: number
  normalization?: Record<string, unknown>
  boundsNormalized?: unknown
  renderHint?: Record<string, unknown>
  segments?: unknown[]
  selectedRegionId?: string
}

export interface AgentVisualizationData {
  schemaVersion?: string
  available?: boolean
  sceneId?: string
  sampleId?: string
  assetRoles?: string[]
  ortho?: AgentVisualizationOrthoData
  riskOverlays?: AgentRiskOverlayData[]
  evidenceMetrics?: AgentEvidenceMetricsData
  changeComparison?: AgentChangeComparisonData
  pointCloud?: AgentPointCloudVisualizationData
  sceneQuality?: Record<string, unknown>
}

export interface AgentResultSnapshotData {
  schemaVersion?: string
  caseId?: string
  caseStatus?: string
  caseRiskLevel?: string
  caseTitle?: string
  caseAssignee?: string
  caseCreatedAt?: string
  taskId?: string
  taskText?: string
  sceneId?: string
  sampleId?: string
  status?: string
  case?: AgentResultCaseData
  taskIntent?: unknown
  programBundle?: unknown
  selectedProgram?: unknown
  evidencePack?: unknown
  changePack?: unknown
  visualization?: AgentVisualizationData
  riskCards?: unknown[]
  recommendationCards?: unknown[]
  workOrders?: unknown[]
  trace?: AgentTraceItem[]
  errors?: AgentErrorItem[]
  [key: string]: unknown
}

// 规范化 API 根地址，避免拼接路径时出现重复斜杠。
function normalizeBaseUrl(url: string) {
  return url.trim().replace(/\/+$/, '')
}

export const API_CONFIG = {
  baseUrl: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL),
  timeoutMs: 15_000,
  successCode: API_SUCCESS_CODE,
} as const

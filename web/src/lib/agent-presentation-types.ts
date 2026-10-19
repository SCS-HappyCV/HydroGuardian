export type AgentDecisionType =
  | 'direct_answer'
  | 'tool_call'
  | 'workflow'
  | 'clarification'
  | 'abstain'

export type AgentExecutionStatus =
  | 'idle'
  | 'preparing'
  | 'running'
  | 'paused'
  | 'completed'
  | 'review_required'
  | 'clarification_required'
  | 'abstained'
  | 'blocked'
  | 'cancelled'
  | 'failed'

export type AgentWorkflowStepStatus = 'pending' | 'running' | 'completed' | 'skipped' | 'failed'
export type AgentCapabilityStatus = 'available' | 'degraded' | 'unavailable' | 'mock'
export type AgentQualityVerdict = 'passed' | 'limited' | 'review_required' | 'unavailable'
export type AgentQualityCheckStatus = 'passed' | 'warning' | 'failed' | 'unknown'

export interface AgentTaskInput {
  taskId?: string
  taskText: string
  sceneId?: string
  sampleId?: string
  assetRoles?: string[]
  scenarioId?: string
}

export interface AgentTaskView {
  taskId: string
  taskText: string
  sceneId: string
  sampleId?: string
  normalizedTarget: string
  objective: string
  spatialConstraints: string[]
  requiredAssets: string[]
  availableAssets: string[]
  missingAssets: string[]
}

export interface AgentDecisionView {
  type: AgentDecisionType
  title: string
  summary: string
  reasonCode?: string
  selectedTools: string[]
  missingInputs: string[]
  reviewRequired: boolean
}

export interface AgentCapabilityView {
  capabilityId: string
  name: string
  category: 'perception' | 'analysis' | 'verification' | 'business'
  status: AgentCapabilityStatus
  summary: string
}

export interface AgentWorkflowStepView {
  stepId: string
  title: string
  capabilityId: string
  capabilityName: string
  dependsOn: string[]
  status: AgentWorkflowStepStatus
  summary: string
  durationMs?: number
  artifactRefs: string[]
  warnings: string[]
  origin?: 'planner' | 'planned' | 'runtime' | 'verification'
  executor?: string
  verificationPolicy?: 'auto' | 'required' | 'skip'
}

export interface AgentWorkflowView {
  workflowId: string
  title: string
  summary: string
  progress: number
  steps: AgentWorkflowStepView[]
}

export interface AgentResponseOption {
  optionId: string
  label: string
  value: string
}

export interface AgentResponseView {
  kind: 'answer' | 'clarification' | 'abstention'
  title: string
  content: string
  evidenceSummary: string[]
  options?: AgentResponseOption[]
  suggestedActions: string[]
}

export interface AgentArtifactView {
  artifactId: string
  role: string
  title: string
  mediaType: string
  previewUrl?: string
  downloadUrl?: string
  coordinateMode?: string
  availableAtStep: number
      metadata?: Record<string, unknown>
}

export interface AgentLanguageResultView {
  taskType: 'class' | 'attribute' | 'relation' | 'unknown'
  taskTypeLabel: string
  appliedThreshold?: number
  selectedPoints?: number
  selectedRatio?: number
  executionConfidence?: number
  noTarget: boolean
  modelNoTarget: boolean
  calibratedNoTarget: boolean
  abstained: boolean
  query?: string
  programSummary: string[]
  artifactRefs: string[]
}

export interface AgentSemanticClassView {
  classId: number
  className: string
  pointCount: number
  pointRatio: number
  meanConfidence?: number
}

export interface AgentSemanticResultView {
  mode: 'point'
  modeLabel: string
  numPoints?: number
  numPresentClasses?: number
  imageValidated: boolean
  imageUsed: boolean
  inferenceMode: string
  classes: AgentSemanticClassView[]
  artifactRefs: string[]
}

export interface AgentGeometryStatsView {
  pointCount: number
  pointRatio: number
  centroid?: [number, number, number]
  bboxMin?: [number, number, number]
  bboxMax?: [number, number, number]
  elevationMin?: number
  elevationMax?: number
  elevationMean?: number
  elevationMedian?: number
}

export interface AgentGeometryMeasurementView {
  label: string
  value: number
  unit: string
}

export interface AgentGeometryResultView {
  operation: 'class_statistics' | 'near' | 'above' | 'pair_distance' | 'elevation_difference' | 'unknown'
  operationLabel: string
  outcome: 'result' | 'no_target' | 'no_reference' | 'unknown'
  outcomeLabel: string
  targetClassId?: number
  targetClassName: string
  referenceClassId?: number
  referenceClassName?: string
  numPoints?: number
  selectedPoints?: number
  selectedTargetRatio?: number
  target?: AgentGeometryStatsView
  result?: AgentGeometryStatsView
  reference?: AgentGeometryStatsView
  measurements: AgentGeometryMeasurementView[]
  artifactRefs: string[]
}

export interface AgentEvidenceRegionView {
  regionId: string
  label: string
  status: 'risk' | 'review_required' | 'excluded'
  score?: number
  artifactRefs: string[]
  summary: string
  bboxPixel?: { x: number; y: number; width: number; height: number }
  polygonPixel?: Array<{ x: number; y: number }>
  projectedCenter?: { x: number; y: number }
  geographicCenter?: { longitude: number; latitude: number }
  geographicBBox?: { west: number; south: number; east: number; north: number }
}

export interface AgentSpatialAssetView {
  role: string
  sourceType: 'raster' | 'point_cloud' | 'unknown'
  epsg: number
  crsName: string
  horizontalUnit: string
  projectedBounds?: { minX: number; minY: number; maxX: number; maxY: number }
  geographicBounds?: { west: number; south: number; east: number; north: number }
  center?: { longitude: number; latitude: number }
  raster?: { width: number; height: number; pixelSizeX: number; pixelSizeY: number; transform: number[] }
  pointCloud?: { pointCount?: number; elevationMin?: number; elevationMax?: number }
  normalized: boolean
}

export interface AgentSpatialContextView {
  status: 'ready' | 'partial'
  primary: AgentSpatialAssetView
  assets: AgentSpatialAssetView[]
  alignmentErrorMeters?: number
}

export interface AgentEvidenceView {
  status: 'pending' | 'collecting' | 'ready' | 'limited' | 'unavailable'
  summary: string
  artifacts: AgentArtifactView[]
  regions: AgentEvidenceRegionView[]
  languageResult?: AgentLanguageResultView
  semanticResult?: AgentSemanticResultView
  geometryResult?: AgentGeometryResultView
}

export interface AgentQualityCheckView {
  checkId: string
  label: string
  status: AgentQualityCheckStatus
  summary: string
}

export interface AgentQualityMeasurementView {
  key: string
  label: string
  value: number
  format: 'count' | 'percent' | 'number'
}

export interface AgentQualityReportView {
  reportId: string
  sourceTool?: string
  sourceToolLabel: string
  verdict: AgentQualityVerdict
  score?: number
  abstentionRecommended: boolean
  checks: AgentQualityCheckView[]
  measurements: AgentQualityMeasurementView[]
  artifactRefs: string[]
}

export interface AgentQualityView {
  verdict: AgentQualityVerdict
  confidence?: number
  uncertainty?: number
  checks: AgentQualityCheckView[]
  warnings: string[]
  recommendedAction?: string
  reports?: AgentQualityReportView[]
}

export interface AgentRiskView {
  riskId: string
  candidateId?: string
  regionId: string
  ruleId?: string
  sourceTool?: string
  title: string
  riskType: string
  riskLevel: 'high' | 'medium' | 'low' | 'review_required'
  score?: number
  scoreKind?: 'evidence_strength' | string
  summary: string
  evidenceRefs: string[]
  reviewRequired: boolean
  qualityGate?: {
    status: 'passed' | 'review_required'
    verdict: string
    score?: number
    abstentionRecommended: boolean
    automationAllowed: boolean
    reasons: string[]
  }
}

export interface AgentWorkOrderView {
  workOrderId: string
  riskId: string
  title: string
  status: 'draft' | 'pending' | 'processing' | 'review' | 'closed'
  recommendedAction: string
}

export interface AgentBusinessView {
  risks: AgentRiskView[]
  recommendations: string[]
  workOrders: AgentWorkOrderView[]
}

export interface AgentTraceView {
  traceId: string
  stage: string
  level: 'info' | 'warning' | 'error'
  message: string
  timestamp: string
  category?: 'planning' | 'expert' | 'artifact' | 'quality' | 'system'
  tool?: string
  toolLabel?: string
  workerId?: string
  phase?: string
  progress?: number
  attempt?: number
}

export interface AgentDisplayError {
  code:
    | 'INPUT_REQUIRED'
    | 'CAPABILITY_OFFLINE'
    | 'QUALITY_REJECTED'
    | 'EXECUTION_FAILED'
    | 'ARTIFACT_MISSING'
    | 'PERSIST_FAILED'
  title: string
  message: string
  retryable: boolean
  suggestedAction?: string
  traceId?: string
}

export interface AgentPresentationSnapshot {
  schemaVersion: 'agent-presentation.v2'
  snapshotId: string
  scenarioId: string
  sequence: number
  status: AgentExecutionStatus
  task: AgentTaskView
  decision: AgentDecisionView
  capabilities: AgentCapabilityView[]
  workflow?: AgentWorkflowView
  response?: AgentResponseView
  evidence: AgentEvidenceView
  quality: AgentQualityView
  spatial?: AgentSpatialContextView
  business: AgentBusinessView
  trace: AgentTraceView[]
  errors: AgentDisplayError[]
  createdAt: string
}

export interface AgentDemoTimelineItem {
  atMs: number
  snapshot: AgentPresentationSnapshot
}

export interface AgentDemoScenario {
  scenarioId: string
  title: string
  description: string
  taskText: string
  decisionType: AgentDecisionType
  aliases: string[]
  timeline: AgentDemoTimelineItem[]
  finalRoute: string
}

export interface AgentDemoSession {
  version: 1
  scenarioId: string
  taskId: string
  taskInput: AgentTaskInput
  currentStep: number
  status: AgentExecutionStatus
  playbackRate: number
  startedAt?: string
  updatedAt: string
}

export interface AgentPresentationProvider {
  createTask(input: AgentTaskInput): Promise<AgentPresentationSnapshot>
  getSnapshot(taskId: string): AgentPresentationSnapshot | undefined
  start(taskId: string): AgentPresentationSnapshot | undefined
  pause(taskId: string): AgentPresentationSnapshot | undefined
  resume(taskId: string): AgentPresentationSnapshot | undefined
  advance(taskId: string): AgentPresentationSnapshot | undefined
  complete(taskId: string): AgentPresentationSnapshot | undefined
  resetScenario(scenarioId: string): void
}

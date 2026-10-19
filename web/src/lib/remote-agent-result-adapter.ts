import { remoteAgentApi } from '@/api/remote-agent-api'
import type {
  AgentArtifactView,
  AgentBusinessView,
  AgentEvidenceRegionView,
  AgentLanguageResultView,
  AgentSemanticResultView,
  AgentGeometryResultView,
  AgentGeometryStatsView,
  AgentQualityCheckStatus,
  AgentQualityReportView,
  AgentQualityView,
  AgentRiskView,
  AgentSpatialAssetView,
  AgentSpatialContextView,
} from '@/lib/agent-presentation-types'
import type { RemoteAgentJob, RemoteAgentStep } from '@/lib/remote-agent-types'

interface ArtifactSource {
  artifactId: string
  role: string
  stepIndex: number
  tool?: string
  coordinateMode?: string
  metrics?: Record<string, unknown>
}

interface ChangeRegionPayload {
  image_size_hw?: unknown
  threshold?: unknown
  changed_ratio?: unknown
  regions?: unknown
}

interface QualityReportPayload {
  source_tool?: unknown
  verdict?: unknown
  quality_score?: unknown
  abstention_recommended?: unknown
  checks?: unknown
  measurements?: unknown
}

interface ClassSummaryPayload {
  num_points?: unknown
  num_present_classes?: unknown
  classes?: unknown
  inference_mode?: unknown
  image_validated?: unknown
  image_used?: unknown
}

interface GeometryReportPayload {
  operation?: unknown
  outcome?: unknown
  num_points?: unknown
  target_class_id?: unknown
  reference_class_id?: unknown
  target?: unknown
  reference?: unknown
  result?: unknown
  selected_target_ratio?: unknown
  distance_threshold_m?: unknown
  z_margin_m?: unknown
  reference_median_elevation_m?: unknown
  horizontal_distance_m?: unknown
  spatial_distance_m?: unknown
  elevation_difference_m?: unknown
}

interface RemoteRiskCandidatePayload {
  schema_version?: unknown
  candidate_id?: unknown
  rule_id?: unknown
  source_tool?: unknown
  risk_type?: unknown
  title?: unknown
  risk_level?: unknown
  score?: unknown
  score_kind?: unknown
  summary?: unknown
  review_required?: unknown
  recommendation?: unknown
  evidence_refs?: unknown
  region_scope?: unknown
  quality_gate?: unknown
}

export interface RemoteAgentAdaptedResult {
  artifacts: AgentArtifactView[]
  regions: AgentEvidenceRegionView[]
  quality: AgentQualityView
  business: AgentBusinessView
  languageResult?: AgentLanguageResultView
  semanticResult?: AgentSemanticResultView
  geometryResult?: AgentGeometryResultView
  spatial?: AgentSpatialContextView
}

const artifactTitles: Record<string, string> = {
  before_image_path: '巡查前时相影像',
  after_image_path: '巡查后时相影像',
  image_path: '任务影像',
  point_cloud_path: '任务点云',
  point_labels: '点云语义标签',
  class_masks: '类别分割掩膜',
  class_probabilities: '类别置信度',
  class_summary: '场景类别摘要',
  projection_metadata: '多模态投影说明',
  change_mask: '变化检测掩膜',
  change_probability_map: '变化概率图',
  change_regions: '变化区域报告',
  target_mask: '目标点云掩膜',
  target_probabilities: '目标置信度',
  point_visualization: '三维结果预览',
  sampling_metadata: '点云采样说明',
  compiled_program: '空间推理程序',
  relation_mask: '空间关系掩膜',
  geometry_report: '空间关系报告',
  quality_report: '质量验证报告',
  diagnostic_overlay: '质量诊断图',
}

const qualityCheckLabels: Record<string, string> = {
  manifest_tool: '专家来源一致性',
  source_status: '源结果完整性',
  real_prediction: '真实推理验证',
  label_space: '语义标签空间',
  point_count_consistency: '点数一致性',
  probability_integrity: '概率数据完整性',
  confidence: '置信度检查',
  non_empty_result: '非空结果检查',
  target_mask_integrity: '目标掩膜完整性',
  confidence_metadata: '置信度元数据',
  binary_mask: '变化掩膜二值性',
  image_size_consistency: '影像尺寸一致性',
  relation_mask_integrity: '空间关系掩膜完整性',
  supported_source: '结果类型支持度',
  cross_expert_consistency: '跨专家结果一致性',
}

const qualitySourceLabels: Record<string, string> = {
  point_semantic_segmentation: '点云语义分析',
  image_change_detection: '前后时相变化检测',
  language_guided_point_segmentation: '语言引导点云定位',
  geometry_relation_analysis: '空间几何关系分析',
}

const qualityMeasurementLabels: Record<string, { label: string; format: 'count' | 'percent' | 'number' }> = {
  num_predictions: { label: '预测点数', format: 'count' },
  dominant_class_ratio: { label: '主导类别占比', format: 'percent' },
  mean_confidence: { label: '平均置信度', format: 'percent' },
  low_confidence_ratio: { label: '低置信结果占比', format: 'percent' },
  selected_points: { label: '命中点数', format: 'count' },
  selected_target_ratio: { label: '目标命中比例', format: 'percent' },
  changed_pixels: { label: '变化像素数', format: 'count' },
  changed_ratio: { label: '变化像素占比', format: 'percent' },
  comparison_agreement: { label: '跨专家一致率', format: 'percent' },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function artifactId(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const match = /^artifact:\/\/([A-Za-z0-9_-]+)$/.exec(value)
  return match?.[1]
}

function numeric(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function booleanValue(value: unknown): boolean {
  return value === true
}

function artifactMap(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) return {}
  return isRecord(value.artifacts) ? value.artifacts : {}
}

function collectNestedResults(value: unknown): Record<string, unknown>[] {
  if (!isRecord(value)) return []
  const results = [value]
  for (const key of ['result', 'verification_result']) {
    if (isRecord(value[key])) results.push(...collectNestedResults(value[key]))
  }
  if (Array.isArray(value.steps)) {
    for (const step of value.steps) results.push(...collectNestedResults(step))
  }
  if (isRecord(value.workflow_result)) results.push(...collectNestedResults(value.workflow_result))
  return results
}

function collectArtifactSources(job: RemoteAgentJob, steps: RemoteAgentStep[], terminalArtifacts: Record<string, string>): ArtifactSource[] {
  const sources = new Map<string, ArtifactSource>()
  const add = (role: string, uri: unknown, stepIndex: number, result?: Record<string, unknown>, tool?: string) => {
    const id = artifactId(uri)
    if (!id || sources.has(id)) return
    sources.set(id, {
      artifactId: id,
      role: role.includes('.') ? role.split('.').at(-1) || role : role,
      stepIndex,
      tool: tool || (typeof result?.tool === 'string' ? result.tool : undefined),
      coordinateMode: typeof result?.coordinate_space === 'string' ? result.coordinate_space : undefined,
      metrics: isRecord(result?.metrics) ? result.metrics : undefined,
    })
  }

  Object.entries(job.submission.assets || {}).forEach(([role, uri]) => add(role, uri, 0))
  const latestExecutionNumber = Math.max(...steps.map((step) => {
    const match = new RegExp(`^${job.job_id}_a(\\d+)_`).exec(step.step_id)
    return match ? Number(match[1]) : 0
  }), 0)
  const currentAttemptPrefix = latestExecutionNumber > 0 ? `${job.job_id}_a${latestExecutionNumber}_` : undefined
  const numberedAttemptPattern = new RegExp(`^${job.job_id}_a\\d+_`)
  const currentSteps = currentAttemptPrefix
    ? steps.filter((step) => step.step_id.startsWith(currentAttemptPrefix) || !numberedAttemptPattern.test(step.step_id))
    : steps
  currentSteps.forEach((step, index) => {
    collectNestedResults(step.result).forEach((result) => {
      Object.entries(artifactMap(result)).forEach(([role, uri]) => add(role, uri, index + 1, result, step.tool))
    })
  })
  collectNestedResults(job.result).forEach((result) => {
    Object.entries(artifactMap(result)).forEach(([role, uri]) => add(role, uri, Math.max(1, currentSteps.length), result))
  })
  Object.entries(terminalArtifacts).forEach(([role, uri]) => add(role, uri, Math.max(1, currentSteps.length)))
  return [...sources.values()]
}

function guessedMediaType(role: string): string {
  if (['before_image_path', 'after_image_path', 'image_path', 'change_mask', 'diagnostic_overlay'].includes(role)) return 'image/png'
  if (role.endsWith('report') || role.endsWith('metadata') || role === 'compiled_program' || role === 'change_regions' || role === 'class_summary' || role === 'manifest') return 'application/json'
  return 'application/octet-stream'
}

async function loadArtifact(source: ArtifactSource): Promise<{ view: AgentArtifactView; json?: Record<string, unknown> }> {
  const record = await remoteAgentApi.getArtifact(source.artifactId).catch((): undefined => undefined)
  const mediaType = record?.media_type || guessedMediaType(source.role)
  const isJson = mediaType.includes('json') || guessedMediaType(source.role).includes('json')
  const isImage = mediaType.startsWith('image/')
  let downloadUrl: string | undefined
  let json: Record<string, unknown> | undefined

  const isPointCloud = source.role === 'point_cloud_path' || /\.(las|laz)$/i.test(record?.object_key || '')
  const isVisualizationArray = ['target_mask', 'target_probabilities', 'point_visualization', 'relation_mask', 'point_labels', 'class_masks', 'class_probabilities'].includes(source.role)
  if (isJson || isImage || isPointCloud || isVisualizationArray) downloadUrl = await remoteAgentApi.getDownloadUrl(source.artifactId).catch((): undefined => undefined)
  const needsRasterPreview = isImage && (
    /tiff?/i.test(mediaType)
    || ['before_image_path', 'after_image_path', 'image_path'].includes(source.role)
    || (record?.size_bytes || 0) > 8 * 1024 * 1024
  )
  if (isJson && downloadUrl) {
    const request = new AbortController()
    const timeout = setTimeout(() => request.abort(), 8000)
    try {
      json = await fetch(downloadUrl, { signal: request.signal })
        .then(async (response) => response.ok ? response.json() as Promise<unknown> : undefined)
        .then((payload) => isRecord(payload) ? payload : undefined)
        .catch((): undefined => undefined)
    } finally {
      clearTimeout(timeout)
    }
  }

  return {
    view: {
      artifactId: source.artifactId,
      role: source.role,
      title: artifactTitles[source.role] || source.role.replace(/[._]/g, ' '),
      mediaType,
      previewUrl: isImage ? (needsRasterPreview ? remoteAgentApi.getPreviewUrl(source.artifactId) : downloadUrl) : undefined,
      downloadUrl,
      coordinateMode: source.coordinateMode,
      availableAtStep: source.stepIndex,
      metadata: {
        tool: source.tool,
        sizeBytes: record?.size_bytes,
        sha256: record?.sha256,
        objectKey: record?.object_key,
        metrics: source.metrics,
        report: ['change_regions', 'geometry_report', 'quality_report', 'compiled_program', 'sampling_metadata', 'class_summary', 'projection_metadata'].includes(source.role) ? json : undefined,
        spatial: isRecord(record?.metadata?.spatial) ? record.metadata.spatial : undefined,
      },
    },
    json,
  }
}

const languageTaskLabels: Record<AgentLanguageResultView['taskType'], string> = {
  class: '类别目标定位',
  attribute: '属性约束定位',
  relation: '空间关系定位',
  unknown: '语言目标定位',
}

function languageTaskType(value: unknown): AgentLanguageResultView['taskType'] {
  return value === 'class' || value === 'attribute' || value === 'relation' ? value : 'unknown'
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function buildProgramSummary(program: Record<string, unknown> | undefined): string[] {
  if (!program) return []
  const summary: string[] = []
  const target = typeof program.target === 'string' ? program.target : typeof program.target_class === 'string' ? program.target_class : undefined
  if (target) summary.push(`目标：${target}`)
  const attributes = stringList(program.attributes)
  if (attributes.length) summary.push(`属性：${attributes.join('、')}`)
  if (Array.isArray(program.relations) && program.relations.length) {
    const relations = program.relations.filter(isRecord).map((relation) => {
      const type = typeof relation.type === 'string' ? relation.type : '空间关系'
      const reference = typeof relation.reference === 'string' ? relation.reference : typeof relation.reference_class === 'string' ? relation.reference_class : ''
      return reference ? `${type} ${reference}` : type
    })
    if (relations.length) summary.push(`关系：${relations.join('、')}`)
  }
  const steps = Array.isArray(program.steps) ? program.steps.length : 0
  if (steps) summary.push(`推理步骤：${steps} 步`)
  return summary
}

function buildLanguageResult(
  job: RemoteAgentJob,
  steps: RemoteAgentStep[],
  loaded: Array<{ view: AgentArtifactView; json?: Record<string, unknown> }>,
): AgentLanguageResultView | undefined {
  const nestedResults = [
    ...steps.flatMap((step) => collectNestedResults(step.result)),
    ...collectNestedResults(job.result),
  ]
  const result = nestedResults.find((item) => item.tool === 'language_guided_point_segmentation')
  if (!result) return undefined
  const metrics = isRecord(result.metrics) ? result.metrics : {}
  const compiled = loaded.find((item) => item.view.role === 'compiled_program')?.json
  const diagnostics = isRecord(compiled?.inference_diagnostics) ? compiled.inference_diagnostics : {}
  const selectedProgram = isRecord(compiled?.selected_program) ? compiled.selected_program : undefined
  const type = languageTaskType(metrics.inferred_task_type ?? diagnostics.inferred_task_type)
  const artifactRefs = loaded
    .filter((item) => ['target_mask', 'target_probabilities', 'sampling_metadata', 'compiled_program'].includes(item.view.role))
    .map((item) => item.view.artifactId)
  return {
    taskType: type,
    taskTypeLabel: languageTaskLabels[type],
    appliedThreshold: numeric(metrics.applied_mask_threshold) ?? numeric(diagnostics.applied_mask_threshold),
    selectedPoints: numeric(metrics.selected_points),
    selectedRatio: numeric(metrics.selected_ratio),
    executionConfidence: numeric(metrics.execution_confidence),
    noTarget: booleanValue(metrics.no_target),
    modelNoTarget: booleanValue(metrics.model_no_target ?? diagnostics.model_no_target),
    calibratedNoTarget: booleanValue(metrics.calibrated_no_target ?? diagnostics.calibrated_no_target),
    abstained: booleanValue(metrics.abstained),
    query: typeof compiled?.query === 'string' ? compiled.query : job.submission.query,
    programSummary: buildProgramSummary(selectedProgram),
    artifactRefs,
  }
}

function buildSemanticResult(
  job: RemoteAgentJob,
  steps: RemoteAgentStep[],
  loaded: Array<{ view: AgentArtifactView; json?: Record<string, unknown> }>,
): AgentSemanticResultView | undefined {
  const nestedResults = [
    ...steps.flatMap((step) => collectNestedResults(step.result)),
    ...collectNestedResults(job.result),
  ]
  const result = nestedResults.find((item) => item.tool === 'point_semantic_segmentation')
  if (!result) return undefined
  const metrics = isRecord(result.metrics) ? result.metrics : {}
  const summary = loaded.find((item) => item.view.role === 'class_summary')?.json as ClassSummaryPayload | undefined
  const mode = 'point'
  const classes = Array.isArray(summary?.classes) ? summary.classes.filter(isRecord).map((item) => ({
    classId: numeric(item.class_id) ?? 0,
    className: typeof item.class_name === 'string' ? item.class_name : `类别 ${String(item.class_id ?? '')}`,
    pointCount: numeric(item.point_count) ?? 0,
    pointRatio: numeric(item.point_ratio) ?? 0,
    meanConfidence: numeric(item.mean_confidence),
  })).filter((item) => item.classId > 0) : []
  return {
    mode,
    modeLabel: '点云语义分割',
    numPoints: numeric(summary?.num_points) ?? numeric(metrics.num_points),
    numPresentClasses: numeric(summary?.num_present_classes) ?? numeric(metrics.num_present_classes),
    imageValidated: false,
    imageUsed: false,
    inferenceMode: typeof summary?.inference_mode === 'string' ? summary.inference_mode : 'point_only',
    classes,
    artifactRefs: loaded
      .filter((item) => ['point_labels', 'class_masks', 'class_probabilities', 'class_summary'].includes(item.view.role))
      .map((item) => item.view.artifactId),
  }
}

const geometryClassNames = ['简易棚屋', '混凝土房屋', '水泥道路', '土路', '边坡', '陡坎', '坝体', '菜地', '草地', '旱地', '林地', '裸地', '水岸线', '沟渠', '其他']
const geometryOperationLabels: Record<AgentGeometryResultView['operation'], string> = {
  class_statistics: '目标空间统计', near: '邻近关系分析', above: '高程上方关系', pair_distance: '类别间距离分析', elevation_difference: '高程差分析', unknown: '空间关系分析',
}
const geometryOutcomeLabels: Record<AgentGeometryResultView['outcome'], string> = {
  result: '分析完成', no_target: '未发现目标类别', no_reference: '未发现参照类别', unknown: '结果待确认',
}

function vector3(value: unknown): [number, number, number] | undefined {
  if (!Array.isArray(value) || value.length !== 3) return undefined
  const values = value.map(Number)
  return values.every(Number.isFinite) ? values as [number, number, number] : undefined
}

function geometryStats(value: unknown): AgentGeometryStatsView | undefined {
  if (!isRecord(value)) return undefined
  const elevation = isRecord(value.elevation) ? value.elevation : {}
  return {
    pointCount: numeric(value.point_count) ?? 0,
    pointRatio: numeric(value.point_ratio) ?? 0,
    centroid: vector3(value.centroid_xyz),
    bboxMin: vector3(value.bbox_min_xyz),
    bboxMax: vector3(value.bbox_max_xyz),
    elevationMin: numeric(elevation.minimum),
    elevationMax: numeric(elevation.maximum),
    elevationMean: numeric(elevation.mean),
    elevationMedian: numeric(elevation.median),
  }
}

function buildGeometryResult(
  job: RemoteAgentJob,
  steps: RemoteAgentStep[],
  loaded: Array<{ view: AgentArtifactView; json?: Record<string, unknown> }>,
): AgentGeometryResultView | undefined {
  const nestedResults = [...steps.flatMap((step) => collectNestedResults(step.result)), ...collectNestedResults(job.result)]
  const result = nestedResults.find((item) => item.tool === 'geometry_relation_analysis')
  if (!result) return undefined
  const metrics = isRecord(result.metrics) ? result.metrics : {}
  const report = loaded.find((item) => item.view.role === 'geometry_report')?.json as GeometryReportPayload | undefined
  const operationValue = report?.operation
  const operation: AgentGeometryResultView['operation'] = operationValue === 'class_statistics' || operationValue === 'near' || operationValue === 'above' || operationValue === 'pair_distance' || operationValue === 'elevation_difference' ? operationValue : 'unknown'
  const outcomeValue = report?.outcome ?? metrics.outcome
  const outcome: AgentGeometryResultView['outcome'] = outcomeValue === 'result' || outcomeValue === 'no_target' || outcomeValue === 'no_reference' ? outcomeValue : 'unknown'
  const targetClassId = numeric(report?.target_class_id)
  const referenceClassId = numeric(report?.reference_class_id)
  const measurements: AgentGeometryResultView['measurements'] = []
  const addMeasurement = (label: string, value: unknown, unit = 'm') => { const number = numeric(value); if (number !== undefined) measurements.push({ label, value: number, unit }) }
  addMeasurement('邻近阈值', report?.distance_threshold_m)
  addMeasurement('高程判定余量', report?.z_margin_m)
  addMeasurement('参照中位高程', report?.reference_median_elevation_m)
  for (const [label, stats] of [['平均水平距离', report?.horizontal_distance_m], ['平均空间距离', report?.spatial_distance_m], ['平均高程差', report?.elevation_difference_m]] as const) {
    if (isRecord(stats)) addMeasurement(label, stats.mean)
  }
  return {
    operation,
    operationLabel: geometryOperationLabels[operation],
    outcome,
    outcomeLabel: geometryOutcomeLabels[outcome],
    targetClassId,
    targetClassName: targetClassId && geometryClassNames[targetClassId - 1] || (targetClassId ? `类别 ${targetClassId}` : '目标类别'),
    referenceClassId,
    referenceClassName: referenceClassId ? geometryClassNames[referenceClassId - 1] || `类别 ${referenceClassId}` : undefined,
    numPoints: numeric(report?.num_points) ?? numeric(metrics.num_points),
    selectedPoints: numeric(metrics.selected_points) ?? geometryStats(report?.result)?.pointCount,
    selectedTargetRatio: numeric(report?.selected_target_ratio) ?? numeric(metrics.selected_target_ratio),
    target: geometryStats(report?.target),
    result: geometryStats(report?.result),
    reference: geometryStats(report?.reference),
    measurements,
    artifactRefs: loaded.filter((item) => ['relation_mask', 'geometry_report'].includes(item.view.role)).map((item) => item.view.artifactId),
  }
}

function qualityStatus(value: unknown): AgentQualityCheckStatus {
  if (value === 'passed' || value === 'warning' || value === 'failed') return value
  return 'unknown'
}

function qualityVerdict(value: unknown): AgentQualityView['verdict'] {
  return value === 'passed' ? 'passed' : value === 'warning' ? 'limited' : value === 'failed' ? 'review_required' : 'unavailable'
}

function buildQualityReport(report: QualityReportPayload, reportId: string, artifactRefs: string[]): AgentQualityReportView {
  const score = numeric(report.quality_score)
  const checks = Array.isArray(report.checks) ? report.checks.filter(isRecord).map((check, index) => {
    const name = typeof check.name === 'string' ? check.name : `check-${index + 1}`
    const status = qualityStatus(check.status)
    const label = qualityCheckLabels[name] || name.replace(/[._]/g, ' ')
    return {
      checkId: `${reportId}:${name}`,
      label,
      status,
      summary: status === 'passed' ? `${label}检查通过` : status === 'warning' ? `${label}存在限制，建议结合原始证据复核` : status === 'failed' ? `${label}未通过，不能继续自动判定` : `${label}状态待确认`,
    }
  }) : []
  const sourceTool = typeof report.source_tool === 'string' ? report.source_tool : undefined
  const measurements = isRecord(report.measurements) ? Object.entries(report.measurements).flatMap(([key, value]) => {
    const definition = qualityMeasurementLabels[key]
    const number = numeric(value)
    return definition && number !== undefined ? [{ key, label: definition.label, value: number, format: definition.format }] : []
  }) : []
  return {
    reportId,
    sourceTool,
    sourceToolLabel: sourceTool ? qualitySourceLabels[sourceTool] || sourceTool.replace(/[._]/g, ' ') : '专家结果',
    verdict: qualityVerdict(report.verdict),
    score,
    abstentionRecommended: booleanValue(report.abstention_recommended),
    checks,
    measurements,
    artifactRefs,
  }
}

function buildQuality(loaded: Array<{ view: AgentArtifactView; json?: Record<string, unknown> }>): AgentQualityView {
  const reports = loaded.filter((item) => item.view.role === 'quality_report' && item.json).map((item) => {
    const artifactRefs = loaded.filter((candidate) => candidate.view.availableAtStep === item.view.availableAtStep && ['quality_report', 'diagnostic_overlay'].includes(candidate.view.role)).map((candidate) => candidate.view.artifactId)
    return buildQualityReport(item.json as QualityReportPayload, item.view.artifactId, artifactRefs)
  })
  if (!reports.length) return { verdict: 'unavailable', checks: [], warnings: [], reports: [] }
  const checks = reports.flatMap((report) => report.checks)
  const warningChecks = checks.filter((check) => check.status === 'warning' || check.status === 'failed')
  const scores = reports.map((report) => report.score).filter((score): score is number => score !== undefined)
  const confidence = scores.length ? Math.min(...scores) : undefined
  const verdict = reports.some((report) => report.verdict === 'review_required') ? 'review_required' : reports.some((report) => report.verdict === 'limited') ? 'limited' : reports.every((report) => report.verdict === 'passed') ? 'passed' : 'unavailable'
  const abstentionRecommended = reports.some((report) => report.abstentionRecommended)
  return {
    verdict,
    confidence,
    uncertainty: confidence === undefined ? undefined : Math.max(0, 1 - confidence),
    checks,
    warnings: warningChecks.map((check) => `${check.label}：${check.summary}`),
    recommendedAction: abstentionRecommended ? '质量验证建议暂停自动判定并转人工复核。' : warningChecks.length ? '保留质量限制说明，并结合原始证据完成复核。' : '产物完整性验证通过，可继续进行规则研判。',
    reports,
  }
}

function buildChangeRegions(payload: ChangeRegionPayload | undefined, artifactIds: Record<string, string[]>, jobId: string): AgentEvidenceRegionView[] {
  if (!payload || !Array.isArray(payload.regions)) return []
  const refs = [...(artifactIds.change_regions || []), ...(artifactIds.change_mask || []), ...(artifactIds.change_probability_map || [])]
  return payload.regions.filter(isRecord).map((region, index) => {
    const probability = numeric(region.mean_probability) ?? numeric(region.maximum_probability)
    const bbox = Array.isArray(region.bbox_xywh) ? region.bbox_xywh.map(Number) : []
    const area = numeric(region.area_pixels)
    const spatial = isRecord(region.spatial) ? region.spatial : {}
    const projectedCenter = isRecord(spatial.projected_center) ? spatial.projected_center : {}
    const geographicCenter = isRecord(spatial.geographic_center) ? spatial.geographic_center : {}
    const geographicBBox = isRecord(spatial.geographic_bbox) ? spatial.geographic_bbox : {}
    return {
      regionId: `${jobId}-change-${String(region.region_id ?? index + 1)}`,
      label: `变化区域 ${String(region.region_id ?? index + 1)}`,
      status: 'review_required',
      score: probability === undefined ? undefined : Math.round(probability * 100),
      artifactRefs: refs,
      summary: `检测到 ${area === undefined ? '一处' : `${area.toLocaleString('zh-CN')} 像素`}变化，平均置信度${probability === undefined ? '待核验' : `${Math.round(probability * 100)}%`}。`,
      bboxPixel: bbox.length === 4 && bbox.every(Number.isFinite) ? { x: bbox[0], y: bbox[1], width: bbox[2], height: bbox[3] } : undefined,
      projectedCenter: numeric(projectedCenter.x) !== undefined && numeric(projectedCenter.y) !== undefined ? { x: Number(projectedCenter.x), y: Number(projectedCenter.y) } : undefined,
      geographicCenter: numeric(geographicCenter.longitude) !== undefined && numeric(geographicCenter.latitude) !== undefined ? { longitude: Number(geographicCenter.longitude), latitude: Number(geographicCenter.latitude) } : undefined,
      geographicBBox: ['west', 'south', 'east', 'north'].every((key) => numeric(geographicBBox[key]) !== undefined) ? { west: Number(geographicBBox.west), south: Number(geographicBBox.south), east: Number(geographicBBox.east), north: Number(geographicBBox.north) } : undefined,
    }
  })
}

function spatialAsset(value: unknown, fallbackRole = 'scene'): AgentSpatialAssetView | undefined {
  if (!isRecord(value)) return undefined
  const crs = isRecord(value.crs) ? value.crs : {}
  const extent = isRecord(value.extent) ? value.extent : {}
  const projected = isRecord(extent.projected) ? extent.projected : {}
  const geographic = isRecord(extent.geographic) ? extent.geographic : {}
  const raster = isRecord(value.raster) ? value.raster : undefined
  const pointCloud = isRecord(value.point_cloud) ? value.point_cloud : undefined
  const epsg = numeric(crs.code)
  if (epsg === undefined) return undefined
  const projectedBounds = ['min_x', 'min_y', 'max_x', 'max_y'].every((key) => numeric(projected[key]) !== undefined) ? {
    minX: Number(projected.min_x), minY: Number(projected.min_y), maxX: Number(projected.max_x), maxY: Number(projected.max_y),
  } : undefined
  const geographicBounds = ['west', 'south', 'east', 'north'].every((key) => numeric(geographic[key]) !== undefined) ? {
    west: Number(geographic.west), south: Number(geographic.south), east: Number(geographic.east), north: Number(geographic.north),
  } : undefined
  const center = numeric(geographic.center_lon) !== undefined && numeric(geographic.center_lat) !== undefined ? {
    longitude: Number(geographic.center_lon), latitude: Number(geographic.center_lat),
  } : geographicBounds ? {
    longitude: (geographicBounds.west + geographicBounds.east) / 2,
    latitude: (geographicBounds.south + geographicBounds.north) / 2,
  } : undefined
  return {
    role: typeof value.asset_role === 'string' ? value.asset_role : fallbackRole,
    sourceType: value.source_type === 'raster' || value.source_type === 'point_cloud' ? value.source_type : 'unknown',
    epsg,
    crsName: typeof crs.name === 'string' ? crs.name : `EPSG:${epsg}`,
    horizontalUnit: typeof crs.horizontal_unit === 'string' ? crs.horizontal_unit : 'unknown',
    projectedBounds,
    geographicBounds,
    center,
    raster: raster && numeric(raster.width) !== undefined && numeric(raster.height) !== undefined ? {
      width: Number(raster.width), height: Number(raster.height),
      pixelSizeX: numeric(raster.pixel_size_x) ?? 0, pixelSizeY: numeric(raster.pixel_size_y) ?? 0,
      transform: Array.isArray(raster.transform) ? raster.transform.map(Number).filter(Number.isFinite) : [],
    } : undefined,
    pointCloud: pointCloud ? {
      pointCount: numeric(pointCloud.point_count), elevationMin: numeric(pointCloud.elevation_min), elevationMax: numeric(pointCloud.elevation_max),
    } : undefined,
    normalized: crs.normalized === true,
  }
}

function collectSpatialContexts(value: unknown): Record<string, unknown>[] {
  if (!isRecord(value)) return []
  const contexts: Record<string, unknown>[] = []
  if (value.schema_version === 'hydro-spatial-context.v1') contexts.push(value)
  for (const key of ['spatial_context', 'result', 'verification_result', 'workflow_result']) contexts.push(...collectSpatialContexts(value[key]))
  if (Array.isArray(value.steps)) value.steps.forEach((step) => contexts.push(...collectSpatialContexts(step)))
  return contexts
}

function buildSpatialContext(job: RemoteAgentJob, loaded: Array<{ view: AgentArtifactView; json?: Record<string, unknown> }>): AgentSpatialContextView | undefined {
  const byRole = new Map<string, AgentSpatialAssetView>()
  for (const context of collectSpatialContexts(job.result)) {
    const assets = isRecord(context.assets) ? context.assets : {}
    Object.entries(assets).forEach(([role, value]) => {
      const parsed = spatialAsset(value, role)
      if (parsed) byRole.set(parsed.role, parsed)
    })
    const primary = spatialAsset(context.primary, 'scene')
    if (primary && !byRole.has(primary.role)) byRole.set(primary.role, primary)
  }
  loaded.forEach(({ view }) => {
    const raw = isRecord(view.metadata?.spatial) ? view.metadata.spatial : undefined
    const parsed = spatialAsset(raw, view.role)
    if (parsed && !byRole.has(parsed.role)) byRole.set(parsed.role, parsed)
  })
  const assets = [...byRole.values()]
  if (!assets.length) return undefined
  const primary = assets.find((item) => item.role === 'after_image_path') || assets.find((item) => item.role === 'image_path') || assets.find((item) => item.role === 'point_cloud_path') || assets[0]
  const comparable = assets.filter((item) => item.epsg === primary.epsg && item.projectedBounds)
  const alignmentErrorMeters = comparable.length > 1 && primary.projectedBounds ? Math.max(...comparable.flatMap((item) => [
    Math.abs(item.projectedBounds!.minX - primary.projectedBounds!.minX), Math.abs(item.projectedBounds!.minY - primary.projectedBounds!.minY),
    Math.abs(item.projectedBounds!.maxX - primary.projectedBounds!.maxX), Math.abs(item.projectedBounds!.maxY - primary.projectedBounds!.maxY),
  ])) : undefined
  return { status: primary.center ? 'ready' : 'partial', primary, assets, alignmentErrorMeters }
}

function buildBusiness(job: RemoteAgentJob, regions: AgentEvidenceRegionView[], quality: AgentQualityView): AgentBusinessView {
  const payloads = Array.isArray(job.result?.risk_candidates) ? job.result.risk_candidates.filter(isRecord) as RemoteRiskCandidatePayload[] : []
  const risks: AgentRiskView[] = payloads.flatMap((candidate, candidateIndex) => {
    const candidateId = typeof candidate.candidate_id === 'string' ? candidate.candidate_id : `${job.job_id}-candidate-${candidateIndex + 1}`
    const scope = isRecord(candidate.region_scope) ? candidate.region_scope : {}
    const expandedRegions = scope.kind === 'artifact_regions' && regions.length ? regions : [undefined]
    const gate = isRecord(candidate.quality_gate) ? candidate.quality_gate : {}
    const gateStatus = gate.status === 'passed' ? 'passed' : 'review_required'
    const riskLevel: AgentRiskView['riskLevel'] = candidate.risk_level === 'high' || candidate.risk_level === 'medium' || candidate.risk_level === 'low' || candidate.risk_level === 'review_required' ? candidate.risk_level : 'review_required'
    const evidenceRefs = stringList(candidate.evidence_refs).map((value) => artifactId(value) || value)
    return expandedRegions.map((region, regionIndex) => ({
      riskId: region ? `${candidateId}-region-${regionIndex + 1}` : candidateId,
      candidateId,
      regionId: region?.regionId || candidateId,
      ruleId: typeof candidate.rule_id === 'string' ? candidate.rule_id : undefined,
      sourceTool: typeof candidate.source_tool === 'string' ? candidate.source_tool : undefined,
      title: region ? `${typeof candidate.title === 'string' ? candidate.title : '风险候选'} · ${region.label}` : typeof candidate.title === 'string' ? candidate.title : '风险候选',
      riskType: typeof candidate.risk_type === 'string' ? candidate.risk_type : 'agent_risk_candidate',
      riskLevel,
      score: numeric(candidate.score),
      scoreKind: typeof candidate.score_kind === 'string' ? candidate.score_kind : undefined,
      summary: [typeof candidate.summary === 'string' ? candidate.summary : '真实专家结果命中风险候选规则。', region?.summary].filter(Boolean).join(' '),
      evidenceRefs: [...new Set([...evidenceRefs, ...(region?.artifactRefs || [])])],
      reviewRequired: candidate.review_required !== false,
      qualityGate: {
        status: gateStatus,
        verdict: typeof gate.verdict === 'string' ? gate.verdict : 'unavailable',
        score: numeric(gate.score),
        abstentionRecommended: booleanValue(gate.abstention_recommended),
        automationAllowed: booleanValue(gate.automation_allowed),
        reasons: stringList(gate.reasons),
      },
    }))
  })
  const recommendations = [...new Set([
    ...payloads.map((candidate) => typeof candidate.recommendation === 'string' ? candidate.recommendation : '').filter(Boolean),
    ...(risks.length ? [quality.recommendedAction || '结合原始证据和现场情况完成风险确认。'] : []),
  ])]
  return { risks, recommendations, workOrders: [] }
}

export async function adaptRemoteAgentResult(input: {
  job: RemoteAgentJob
  steps: RemoteAgentStep[]
  terminalArtifacts: Record<string, string>
}): Promise<RemoteAgentAdaptedResult> {
  const sources = collectArtifactSources(input.job, input.steps, input.terminalArtifacts)
  const loaded = await Promise.all(sources.map(loadArtifact))
  const artifactIds = loaded.reduce<Record<string, string[]>>((result, item) => {
    const values = result[item.view.role] || []
    values.push(item.view.artifactId)
    result[item.view.role] = values
    return result
  }, {})
  const changeReport = loaded.find((item) => item.view.role === 'change_regions')?.json as ChangeRegionPayload | undefined
  const quality = buildQuality(loaded)
  const regions = buildChangeRegions(changeReport, artifactIds, input.job.job_id)
  const languageResult = buildLanguageResult(input.job, input.steps, loaded)
  const semanticResult = buildSemanticResult(input.job, input.steps, loaded)
  const geometryResult = buildGeometryResult(input.job, input.steps, loaded)
  const spatial = buildSpatialContext(input.job, loaded)
  return {
    artifacts: loaded.map((item) => item.view),
    regions,
    quality,
    business: buildBusiness(input.job, regions, quality),
    languageResult,
    semanticResult,
    geometryResult,
    spatial,
  }
}

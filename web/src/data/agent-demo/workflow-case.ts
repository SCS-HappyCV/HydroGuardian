import type {
  AgentArtifactView,
  AgentDecisionView,
  AgentEvidenceRegionView,
  AgentTaskView,
  AgentWorkflowStepStatus,
  AgentWorkflowStepView,
  AgentWorkflowView,
} from '@/lib/agent-presentation-types'
import { createScenario, createTrace } from './scenario-builder'

const task: AgentTaskView = {
  taskId: 'task-1001',
  taskText: '筛查近水扰动区域，重点识别细长沟渠并排除道路，按风险高低排序',
  sceneId: 'scene-riverbank-001',
  sampleId: 'sample-riverbank-001',
  normalizedTarget: '近水新增细长沟渠与扰动区域',
  objective: '融合点云、几何和前后时相证据形成风险清单',
  spatialConstraints: ['位于水线邻域 30m 内', '连续细长形态', '排除道路及既有硬化带'],
  requiredAssets: ['正射影像', '点云', '前时相影像', '后时相影像'],
  availableAssets: ['正射影像', '点云', '前时相影像', '后时相影像'],
  missingAssets: [],
}

const decision: AgentDecisionView = {
  type: 'workflow',
  title: '将执行多专家协同分析',
  summary: '任务同时包含语义识别、空间关系、时相变化和可靠性验证，需要组织组合工作流。',
  reasonCode: 'MULTI_EVIDENCE_REQUIRED',
  selectedTools: [
    'point_semantic_segmentation',
    'geometry_relation_analysis',
    'image_change_detection',
    'result_quality_verification',
  ],
  missingInputs: [],
  reviewRequired: false,
}

const stepDefinitions = [
  ['understand', '理解巡查任务', 'task_understanding', '任务理解', []],
  ['scene', '检查场景资产', 'scene_asset_check', '场景资产检查', ['understand']],
  ['point', '分析点云语义', 'point_semantic_segmentation', '点云语义分析', ['scene']],
  ['geometry', '计算空间几何关系', 'geometry_relation_analysis', '空间几何关系分析', ['point']],
  ['change', '检测前后时相变化', 'image_change_detection', '前后时相变化检测', ['scene']],
  ['quality', '验证结果质量', 'result_quality_verification', '结果质量验证', ['geometry', 'change']],
  ['business', '生成风险与处置建议', 'business_result_compiler', '风险结果编译', ['quality']],
] as const

function buildWorkflow(statuses: AgentWorkflowStepStatus[], progress: number): AgentWorkflowView {
  const completedSummary: Record<string, string> = {
    understand: '识别近水、细长、排除道路和按风险排序等约束',
    scene: '四类场景资产完整，坐标与时相信息可用',
    point: '已定位水体、岸坡、道路和三个候选区域',
    geometry: '两个候选区域满足近水和细长条件，一个道路区域被排除',
    change: '发现一处明显新增扰动和一处弱变化区域',
    quality: '一个结果通过验证，一个结果因证据冲突转入复核',
    business: '已生成风险卡、处置建议和工单草稿',
  }

  const artifactRefsByStep: Record<string, string[]> = {
    point: ['artifact-point-mask'],
    geometry: ['artifact-geometry-report'],
    change: ['artifact-change-mask'],
    quality: ['artifact-quality-report'],
    business: ['artifact-evidence-pack'],
  }

  const steps: AgentWorkflowStepView[] = stepDefinitions.map((definition, index) => {
    const [stepId, title, capabilityId, capabilityName, dependsOn] = definition
    const status = statuses[index] ?? 'pending'
    return {
      stepId,
      title,
      capabilityId,
      capabilityName,
      dependsOn: [...dependsOn],
      status,
      summary: status === 'completed'
        ? completedSummary[stepId]
        : status === 'running'
          ? `正在${title.replace('检查', '检查').replace('分析', '分析').replace('计算', '计算').replace('检测', '检测').replace('验证', '验证').replace('生成', '生成')}`
          : '等待上游步骤完成',
      durationMs: status === 'completed' ? [620, 480, 1360, 740, 1180, 520, 410][index] : undefined,
      artifactRefs: status === 'completed' ? artifactRefsByStep[stepId] ?? [] : [],
      warnings: stepId === 'quality' && status === 'completed' ? ['候选区域 R-02 的多源证据存在差异'] : [],
    }
  })

  return {
    workflowId: 'workflow-near-water-disturbance',
    title: '近水扰动多专家分析工作流',
    summary: '语义识别、空间几何、时相变化和质量验证协同执行',
    progress,
    steps,
  }
}

const pointArtifact: AgentArtifactView = {
  artifactId: 'artifact-point-mask',
  role: 'point_segmentation_mask',
  title: '点云语义候选区域',
  mediaType: 'application/json',
  coordinateMode: 'scene_normalized',
  availableAtStep: 3,
  metadata: { candidateCount: 3, pointCount: 184260 },
}

const geometryArtifact: AgentArtifactView = {
  artifactId: 'artifact-geometry-report',
  role: 'geometry_relation_report',
  title: '近水与形态关系报告',
  mediaType: 'application/json',
  coordinateMode: 'scene_normalized',
  availableAtStep: 4,
  metadata: { nearestWaterDistance: 12.8, excludedRoadCount: 1 },
}

const changeArtifact: AgentArtifactView = {
  artifactId: 'artifact-change-mask',
  role: 'change_mask',
  title: '前后时相变化掩码',
  mediaType: 'image/png',
  coordinateMode: 'image_pixel',
  availableAtStep: 5,
  metadata: { changeScore: 0.91, changedAreaSquareMeters: 286 },
}

const qualityArtifact: AgentArtifactView = {
  artifactId: 'artifact-quality-report',
  role: 'quality_report',
  title: '结果质量验证报告',
  mediaType: 'application/json',
  availableAtStep: 6,
  metadata: { passedCount: 1, reviewCount: 1 },
}

const evidenceArtifact: AgentArtifactView = {
  artifactId: 'artifact-evidence-pack',
  role: 'evidence_pack',
  title: '多模态风险证据包',
  mediaType: 'application/json',
  availableAtStep: 7,
  metadata: { riskCount: 2 },
}

const regions: AgentEvidenceRegionView[] = [
  {
    regionId: 'region-R01',
    label: 'R-01 新增近水细长扰动',
    status: 'risk',
    score: 92,
    artifactRefs: ['artifact-point-mask', 'artifact-geometry-report', 'artifact-change-mask'],
    summary: '距水线 12.8m，细长形态明显，前后时相存在新增变化。',
    bboxPixel: { x: 608, y: 218, width: 138, height: 82 },
  },
  {
    regionId: 'region-R02',
    label: 'R-02 岸坡弱变化区域',
    status: 'review_required',
    score: 68,
    artifactRefs: ['artifact-point-mask', 'artifact-geometry-report', 'artifact-change-mask'],
    summary: '几何特征符合条件，但时相变化较弱，建议人工复核。',
    bboxPixel: { x: 328, y: 338, width: 112, height: 74 },
  },
  {
    regionId: 'region-X01',
    label: 'X-01 既有道路区域',
    status: 'excluded',
    score: 95,
    artifactRefs: ['artifact-point-mask', 'artifact-geometry-report'],
    summary: '道路语义和硬化带形态明确，已按排除条件过滤。',
    bboxPixel: { x: 164, y: 142, width: 194, height: 46 },
  },
]

export const workflowScenario = createScenario({
  scenarioId: 'near-water-disturbance-workflow',
  title: '近水扰动与疑似沟渠筛查',
  description: '通过点云、几何、时相变化和质量验证形成风险与复核结果。',
  task,
  decisionType: 'workflow',
  aliases: ['近水', '扰动', '沟渠', '细长', '道路', '风险排序', '综合筛查'],
  finalRoute: './risk-workspace.html?taskId=task-1001&caseId=case-near-water-disturbance-001',
  snapshots: [
    {
      sequence: 0,
      atMs: 0,
      status: 'idle',
      decision,
      workflow: buildWorkflow(['pending'], 0),
      trace: [createTrace('trace-wf-00', 'task.created', '巡查任务已创建，等待启动分析')],
    },
    {
      sequence: 1,
      atMs: 500,
      status: 'preparing',
      decision,
      workflow: buildWorkflow(['running'], 8),
      trace: [createTrace('trace-wf-01', 'agent.understand', '正在识别任务目标与空间约束')],
    },
    {
      sequence: 2,
      atMs: 1200,
      status: 'running',
      decision,
      workflow: buildWorkflow(['completed', 'running'], 20),
      trace: [createTrace('trace-wf-02', 'agent.route', '已选择多专家协同工作流')],
    },
    {
      sequence: 3,
      atMs: 2200,
      status: 'running',
      decision,
      workflow: buildWorkflow(['completed', 'completed', 'running'], 38),
      evidence: { status: 'collecting', summary: '正在生成点云语义候选区域' },
      trace: [createTrace('trace-wf-03', 'expert.point', '场景资产检查完成，开始点云语义分析')],
    },
    {
      sequence: 4,
      atMs: 3600,
      status: 'running',
      decision,
      workflow: buildWorkflow(['completed', 'completed', 'completed', 'running', 'running'], 62),
      evidence: {
        status: 'collecting',
        summary: '已形成三个语义候选区域，正在计算几何关系和时相变化',
        artifacts: [pointArtifact],
      },
      trace: [createTrace('trace-wf-04', 'expert.geometry_change', '点云候选区域已生成，几何分析与变化检测正在协同执行')],
    },
    {
      sequence: 5,
      atMs: 5200,
      status: 'running',
      decision,
      workflow: buildWorkflow(['completed', 'completed', 'completed', 'completed', 'completed', 'running'], 82),
      evidence: {
        status: 'ready',
        summary: '点云、几何和时相变化证据已生成',
        artifacts: [pointArtifact, geometryArtifact, changeArtifact],
        regions,
      },
      quality: {
        verdict: 'unavailable',
        checks: [],
        warnings: [],
        recommendedAction: '等待质量验证完成',
      },
      trace: [createTrace('trace-wf-05', 'expert.quality', '多源证据已聚合，正在进行结果质量验证')],
    },
    {
      sequence: 6,
      atMs: 6500,
      status: 'review_required',
      decision: { ...decision, reviewRequired: true },
      workflow: buildWorkflow(['completed', 'completed', 'completed', 'completed', 'completed', 'completed', 'completed'], 100),
      evidence: {
        status: 'ready',
        summary: '已形成两个风险对象和一个排除对象',
        artifacts: [pointArtifact, geometryArtifact, changeArtifact, qualityArtifact, evidenceArtifact],
        regions,
      },
      quality: {
        verdict: 'review_required',
        confidence: 0.89,
        uncertainty: 0.21,
        checks: [
          { checkId: 'mask', label: '区域掩码有效性', status: 'passed', summary: '区域边界与点数满足验证要求' },
          { checkId: 'alignment', label: '多源坐标一致性', status: 'passed', summary: '点云与影像区域已对齐' },
          { checkId: 'consistency', label: '多源证据一致性', status: 'warning', summary: 'R-02 的变化证据弱于几何证据' },
        ],
        warnings: ['R-02 建议由人工确认岸坡弱变化是否属于真实扰动'],
        recommendedAction: 'R-01 可生成工单，R-02 转入人工复核',
      },
      business: {
        risks: [
          {
            riskId: 'risk-agent-001',
            regionId: 'region-R01',
            title: '新增近水细长扰动',
            riskType: 'near_water_disturbance',
            riskLevel: 'high',
            score: 92,
            summary: '新增变化明确且距水线较近，建议尽快现场核查。',
            evidenceRefs: ['artifact-point-mask', 'artifact-geometry-report', 'artifact-change-mask'],
            reviewRequired: false,
          },
          {
            riskId: 'risk-agent-002',
            regionId: 'region-R02',
            title: '岸坡弱变化待确认',
            riskType: 'bank_slope_change',
            riskLevel: 'review_required',
            score: 68,
            summary: '几何和变化证据存在差异，需要人工复核。',
            evidenceRefs: ['artifact-geometry-report', 'artifact-change-mask', 'artifact-quality-report'],
            reviewRequired: true,
          },
        ],
        recommendations: ['优先核查 R-01 是否存在新增开挖或排水沟', '对 R-02 补充近景照片并复核变化边界'],
        workOrders: [
          {
            workOrderId: 'wo-agent-draft-001',
            riskId: 'risk-agent-001',
            title: '近水新增扰动现场核查',
            status: 'draft',
            recommendedAction: '24 小时内完成现场核查并回传照片',
          },
        ],
      },
      trace: [createTrace('trace-wf-06', 'workflow.completed', '分析完成：一个高风险对象，一个对象建议人工复核', 'warning')],
    },
  ],
})

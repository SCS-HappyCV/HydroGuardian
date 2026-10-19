import type { MobileEvidence, MobileRiskLevel, MobileTimelineEvent, MobileWorkOrder, MobileWorkOrderStatus } from '@/domain/workorder'
import { runtimeConfig } from '@/config/runtime'
import type { RemoteWorkorder, RemoteWorkorderEvidence } from './remoteWorkorderTypes'

function numberValue(value: unknown, fallback: number) {
  const result = Number(value)
  return Number.isFinite(result) ? result : fallback
}

function textValue(value: unknown, fallback: string) {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function riskLevel(value: string): MobileRiskLevel {
  if (value === 'high' || value === 'medium') return value
  return 'review_required'
}

function status(order: RemoteWorkorder): MobileWorkOrderStatus {
  if (order.status === 'doing') return 'in_progress'
  if (order.status === 'review') return 'reviewed'
  if (order.status === 'closed') return 'closed'
  return order.assignee_user_id ? 'assigned' : 'todo'
}

function evidenceType(item: RemoteWorkorderEvidence): MobileEvidence['type'] {
  const value = `${item.title} ${String(item.metadata.role || '')} ${artifactRole(item)} ${String(item.metadata.artifact_object_key || '')}`.toLowerCase()
  if (value.includes('变化') || value.includes('change')) return 'change'
  if (value.includes('点云') || value.includes('几何') || value.includes('point')) return 'geometry'
  if (value.includes('规则') || value.includes('空间约束')) return 'rule'
  return 'image'
}

function artifactRole(item: RemoteWorkorderEvidence) {
  const metadata = item.metadata.artifact_metadata
  if (!metadata || typeof metadata !== 'object') return ''
  return String((metadata as Record<string, unknown>).spatial_role || '')
}

function artifactFilename(item: RemoteWorkorderEvidence) {
  const key = String(item.metadata.artifact_object_key || '')
  return key.split('/').pop() || ''
}

function humanFileSize(value: unknown) {
  const bytes = numberValue(value, 0)
  if (!bytes) return ''
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

const artifactLabels: Record<string, { title: string; summary: string; metric: string }> = {
  change_mask: { title: '变化检测掩膜', summary: '标注前后时相中发生显著变化的像素区域', metric: '变化检测结果' },
  change_probability_map: { title: '变化概率图', summary: '保存逐像素变化置信度，供风险区域提取与复核', metric: '像素级概率数据' },
  change_regions: { title: '变化区域清单', summary: '记录变化斑块的空间范围、面积与候选区域', metric: '结构化区域数据' },
  quality_report: { title: '模型质量报告', summary: '记录本次专家分析的输入质量与结果可信度检查', metric: '自动质量核验' },
  diagnostic_overlay: { title: '诊断叠加图', summary: '将模型判定区域叠加到原始影像，便于人工复核', metric: '可视化核验结果' },
  geometry_report: { title: '点云几何分析', summary: '统计高程、坡度与地形结构等三维几何特征', metric: '三维几何报告' },
  relation_mask: { title: '空间关系分析', summary: '表达目标与水域、岸线及重点区域的空间关系', metric: '空间约束结果' },
  segmentation_result: { title: '点云语义分割', summary: '按地物类别标注点云，识别水体、植被、地面与构筑物', metric: '点云分类结果' },
}

function evidencePresentation(item: RemoteWorkorderEvidence) {
  const role = artifactRole(item) || String(item.metadata.role || '')
  const known = artifactLabels[role]
  if (known) return known
  const filename = artifactFilename(item).toLowerCase()
  if (filename.includes('geometry')) return artifactLabels.geometry_report
  if (filename.includes('relation')) return artifactLabels.relation_mask
  if (filename.includes('segment') || filename.includes('semantic')) return artifactLabels.segmentation_result
  if (role === 'before_image_path') return { title: '巡查前时相影像', summary: '作为变化分析基线的历史正射影像', metric: '原始空间证据' }
  if (role === 'after_image_path') return { title: '风险发现时相影像', summary: '用于识别当前地表状态与异常变化', metric: '原始空间证据' }
  if (role === 'image_path') return { title: '任务现场影像', summary: '本次巡查任务使用的现场遥感影像', metric: '原始空间证据' }
  if (role === 'point_cloud_path') return { title: '现场三维点云', summary: '用于地形、结构和地物类别研判的三维点云', metric: '原始三维证据' }
  return {
    title: item.title === 'Agent 研判证据' ? '专家分析产物' : item.title,
    summary: textValue(item.content, '专家模型输出已归档，可追溯至原始任务'),
    metric: '可追溯分析结果',
  }
}

function previewKind(item: RemoteWorkorderEvidence): NonNullable<MobileEvidence['previewKind']> {
  const mediaType = String(item.metadata.artifact_media_type || item.media_type || '').toLowerCase()
  const role = artifactRole(item)
  if (mediaType.startsWith('image/')) return 'image'
  if (mediaType === 'application/json' || role.endsWith('_report') || role === 'change_regions') return 'report'
  return 'dataset'
}

function mapEvidence(order: RemoteWorkorder): MobileEvidence[] {
  const source = order.evidence.filter((item) => item.evidence_type === 'source').slice(0, 6)
  return source.map((item, index) => {
    const rawScore = numberValue(item.metadata.score, order.score)
    const score = Math.round(rawScore <= 1 ? rawScore * 100 : rawScore)
    const presentation = evidencePresentation(item)
    const size = humanFileSize(item.metadata.artifact_size_bytes)
    const kind = previewKind(item)
    const mediaType = String(item.metadata.artifact_media_type || item.media_type || '')
    return {
      id: item.evidence_id,
      type: evidenceType(item),
      title: presentation.title,
      summary: presentation.summary,
      metric: size ? `${presentation.metric} · ${size}` : presentation.metric,
      score: Math.max(0, Math.min(100, score || 80 - index)),
      artifactId: item.artifact_id || undefined,
      previewUrl: item.artifact_id && kind === 'image' ? `${runtimeBaseUrl()}/v1/assets/${encodeURIComponent(item.artifact_id)}/preview?max_dimension=720` : undefined,
      previewKind: kind,
      mediaType: mediaType || undefined,
    }
  })
}

function mapTimeline(order: RemoteWorkorder, mappedStatus: MobileWorkOrderStatus): MobileTimelineEvent[] {
  const events = order.timeline.map((event) => ({
    id: String(event.event_id), label: event.action, detail: event.note || '服务端状态已记录', at: event.created_at, state: 'done' as const,
  }))
  if (events.length) return events.slice(-8).reverse()
  const labels = [
    ['任务创建', 'Agent 已创建风险工单'],
    ['Agent 研判', '多源证据分析结果已归档'],
    ['任务派发', '现场责任人已接收任务'],
    ['现场处置', '等待现场反馈与证据回传'],
    ['人工复核', '等待复核结论与闭环归档'],
  ] as const
  const stage = { todo: 1, assigned: 3, in_progress: 4, reviewed: 5, closed: 5 }[mappedStatus]
  return labels.map(([label, detail], index) => ({
    id: `stage-${index}`, label, detail, at: index < stage ? order.updated_at : '',
    state: index < stage ? 'done' : index === stage ? 'current' : 'pending',
  }))
}

function runtimeBaseUrl() {
  return runtimeConfig.apiBaseUrl
}

export function mapRemoteWorkorder(order: RemoteWorkorder): MobileWorkOrder {
  const snapshot = order.risk_snapshot || {}
  const location = snapshot.location && typeof snapshot.location === 'object'
    ? snapshot.location as Record<string, unknown>
    : {}
  const confidence = Math.round(numberValue(snapshot.confidence, order.score <= 1 ? order.score * 100 : order.score))
  const mappedStatus = status(order)
  const progress = { todo: 20, assigned: 40, in_progress: 60, reviewed: 80, closed: 100 }[mappedStatus]
  return {
    id: order.workorder_id,
    caseId: order.job_id,
    taskId: order.task_id || order.job_id,
    riskId: order.region_id || order.candidate_id,
    title: order.title,
    area: textValue(snapshot.area || snapshot.zone_name || snapshot.location_name, '智能巡查风险区域'),
    riskLevel: riskLevel(order.risk_level),
    status: mappedStatus,
    deadline: order.due_at || order.updated_at,
    distanceMeters: Math.max(0, Math.round(numberValue(snapshot.distance_meters, 0))),
    confidence: Math.max(0, Math.min(100, confidence)),
    uncertainty: Math.max(0, Math.min(100, Math.round(numberValue(snapshot.uncertainty, 100 - confidence)))),
    summary: order.summary,
    recommendedAction: order.recommendation || '请到达现场核验风险范围，并完整回传处置前后证据。',
    assignee: order.assignee_user_id || '待接收',
    reviewer: order.reviewer_user_id || '人工复核员',
    longitude: numberValue(location.longitude, 0),
    latitude: numberValue(location.latitude, 0),
    evidence: mapEvidence(order),
    timeline: mapTimeline(order, mappedStatus),
    progress,
    updatedAt: order.updated_at,
    source: 'remote',
    jobId: order.job_id,
    remoteVersion: order.version,
  }
}

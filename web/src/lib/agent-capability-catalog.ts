import type { AgentCapabilityView } from '@/lib/agent-presentation-types'

export const AGENT_CAPABILITIES: AgentCapabilityView[] = [
  {
    capabilityId: 'point_semantic_segmentation',
    name: '点云语义分析',
    category: 'perception',
    status: 'available',
    summary: '识别水体、岸坡、道路等水利场景地物',
  },
  {
    capabilityId: 'image_change_detection',
    name: '前后时相变化检测',
    category: 'perception',
    status: 'available',
    summary: '对齐前后影像并提取新增变化区域',
  },
  {
    capabilityId: 'language_guided_point_segmentation',
    name: '语言引导点云定位',
    category: 'perception',
    status: 'unavailable',
    summary: '根据自然语言目标定位点云区域',
  },
  {
    capabilityId: 'geometry_relation_analysis',
    name: '空间几何关系分析',
    category: 'analysis',
    status: 'available',
    summary: '计算近水、距离、高差和形态关系',
  },
  {
    capabilityId: 'result_quality_verification',
    name: '结果质量验证',
    category: 'verification',
    status: 'available',
    summary: '检查结果完整性、一致性和不确定性',
  },
]

export function getAgentCapability(capabilityId: string): AgentCapabilityView | undefined {
  return AGENT_CAPABILITIES.find((item) => item.capabilityId === capabilityId)
}

export function cloneAgentCapabilities(): AgentCapabilityView[] {
  return AGENT_CAPABILITIES.map((item) => ({ ...item }))
}

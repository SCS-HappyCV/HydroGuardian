export interface CompiledTaskIntent {
  target: string
  objective: string
  spatialRelations: string[]
  geometryConstraints: string[]
  exclusions: string[]
  ranking: string
  evidenceModalities: string[]
  reviewPolicy: string
}

function includesAny(text: string, keywords: string[]): boolean {
  return keywords.some((keyword) => text.includes(keyword))
}

export function compileTaskIntent(taskText: string): CompiledTaskIntent {
  const text = taskText.trim()
  const isSlopeTask = includesAny(text, ['陡坡', '裸地', '坡面', '边坡'])
  const isChangeTask = includesAny(text, ['扰动', '变化', '新增', '前后', '时相'])
  const isDitchTask = includesAny(text, ['沟渠', '细长', '条带', '开挖']) || (!isSlopeTask && !isChangeTask)

  let target = '近水候选风险区域'
  let objective = '筛查水利场景中的异常候选区域并形成风险清单'
  const geometryConstraints: string[] = []

  if (isSlopeTask) {
    target = '临水陡坡裸地区域'
    objective = '定位高于水线且坡度较大的裸地候选区域'
    geometryConstraints.push('坡度达到风险阈值', '裸地占比显著', '高程高于邻近水线')
  } else if (isDitchTask) {
    target = '近水细长沟渠'
    objective = '定位靠近水线的连续细长地物，并排除道路干扰'
    geometryConstraints.push('连续细长形态', '高长宽比', '局部高程差明显')
  }

  if (isChangeTask) geometryConstraints.push('前后时相存在新增变化')

  const spatialRelations = includesAny(text, ['近水', '靠近水线', '临水', '岸线'])
    ? ['位于水线邻域', '保持与岸线的空间关联']
    : ['限定在所选巡查区域']

  const exclusions = includesAny(text, ['排除道路', '道路'])
    ? ['道路及道路边缘', '既有硬化带']
    : ['低置信度噪声区域']

  const ranking = includesAny(text, ['排序', '风险高低', '优先'])
    ? '按综合风险分数降序'
    : '按候选置信度排序'

  const evidenceModalities = ['正射影像', '点云与几何特征']
  if (isChangeTask) evidenceModalities.push('前后时相变化')

  return {
    target,
    objective,
    spatialRelations,
    geometryConstraints: [...new Set(geometryConstraints)],
    exclusions,
    ranking,
    evidenceModalities,
    reviewPolicy: '证据冲突或综合置信度不足时主动转人工复核',
  }
}


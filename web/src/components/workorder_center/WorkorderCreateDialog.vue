
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import SafeIcon from '@/components/common/SafeIcon.vue'
import * as RiskEventService from '@/data/RiskEventService'
import * as UserService from '@/data/UserService'
import * as WorkorderService from '@/data/WorkorderService'
import * as WorkorderTimelineService from '@/data/WorkorderTimelineService'
import * as WorkorderEvidenceService from '@/data/WorkorderEvidenceService'
import type { RiskEventVO } from '@/data/RiskEventService'
import { buildRiskEvidenceProfile } from '@/lib/risk-evidence'

const props = defineProps<{
  open: boolean
  prefilledRiskId?: string | null
  prefilledCaseId?: string | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', workorder: any): void
}>()

const selectedRiskId = ref('')
const workorderTitle = ref('')
const workorderSummary = ref('')
const selectedAssignee = ref('')
const selectedTemplate = ref('')

const allRisks = computed(() => RiskEventService.getAll())
const selectedRisk = computed(() => {
  if (!selectedRiskId.value) return null
  return RiskEventService.getByIdVO(selectedRiskId.value)
})
const assigneeOptions = computed(() => UserService.getAll().map(u => ({ id: u.id, name: u.name })))
const evidenceProfile = computed(() => selectedRisk.value ? buildRiskEvidenceProfile(selectedRisk.value) : null)

const canCreate = computed(() => {
  return selectedRiskId.value && workorderTitle.value.trim() && selectedAssignee.value
})

const handleRiskSelect = (riskId: string) => {
  selectedRiskId.value = riskId
  const risk = RiskEventService.getById(riskId)
  if (risk) {
    const profile = buildRiskEvidenceProfile(risk)
    workorderTitle.value = risk.level === 'review_required' ? `${risk.title}人工核验` : `${risk.title}现场处置`
    workorderSummary.value = profile.recommendation.action
    selectedTemplate.value = profile.recommendation.template
    selectedAssignee.value = risk.level === 'review_required' ? 'user-004' : 'user-002'
  }
}

const handleCreate = () => {
  if (!canCreate.value) {
    toast.error('请填写必要信息')
    return
  }

  const now = new Date()
  const selectedRiskData = selectedRisk.value
  const profile = evidenceProfile.value
  const newWorkorder = {
    id: `wo-${Date.now()}`,
    title: workorderTitle.value,
    riskId: selectedRiskId.value,
    taskId: selectedRiskData?.taskId,
    caseId: props.prefilledCaseId || selectedRiskData?.caseId,
    assigneeUserId: selectedAssignee.value,
    reviewerUserId: 'user-004',
    ruleId: selectedRisk.value?.ruleId || '',
    templateId: selectedRisk.value?.level === 'review_required' ? 'tpl-a02' : 'tpl-a01',
    status: 'todo' as const,
    priority: selectedRisk.value?.level === 'high' ? 'urgent' as const : 'high' as const,
    dueAt: new Date(now.getTime() + (selectedRisk.value?.level === 'high' ? 2 : 24) * 60 * 60 * 1000).toISOString(),
    createdAt: now.toISOString(),
    updatedAt: now.toISOString(),
    summary: workorderSummary.value,
    aiRecommendation: profile?.recommendation.action,
  }

  const allWorkorders = WorkorderService.getAll()
  allWorkorders.push(newWorkorder)
  WorkorderService.savePersisted(allWorkorders)

  const allTimeline = WorkorderTimelineService.getAll()
  allTimeline.push({
    id: `wot-${Date.now()}`,
    orderId: newWorkorder.id,
    actorUserId: 'user-001',
    action: 'created',
    note: `HydroGuardian 已聚合多模态证据并自动生成“${selectedTemplate.value}”。`,
    createdAt: now.toISOString(),
  })
  WorkorderTimelineService.savePersisted(allTimeline)

  const allEvidence = WorkorderEvidenceService.getAll()
  allEvidence.push({
    id: `evi-${Date.now()}`,
    orderId: newWorkorder.id,
    evidenceType: 'before',
    title: 'AI 多模态风险证据包',
    content: selectedRiskData?.evidenceSummary || '已关联正射影像、点云几何和时相变化证据。',
    createdAt: now.toISOString(),
  })
  WorkorderEvidenceService.savePersisted(allEvidence)

  toast.success('工单创建成功')
  emit('created', newWorkorder)

  selectedRiskId.value = ''
  workorderTitle.value = ''
  workorderSummary.value = ''
  selectedAssignee.value = ''
  selectedTemplate.value = ''
}

function resetForm() {
  selectedRiskId.value = ''
  workorderTitle.value = ''
  workorderSummary.value = ''
  selectedAssignee.value = ''
  selectedTemplate.value = ''
}

function applyPrefill() {
  if (props.prefilledRiskId) handleRiskSelect(props.prefilledRiskId)
}

onMounted(applyPrefill)

watch(() => props.open, (newVal) => {
  if (newVal) applyPrefill()
  else resetForm()
})
</script>

<template>
  <Dialog :open="open" @update:open="(val) => !val && emit('close')">
    <DialogContent class="max-w-2xl flex flex-col max-h-[80vh]">
      <DialogHeader class="flex-shrink-0">
        <DialogTitle>生成 AI 处置工单</DialogTitle>
        <DialogDescription>
          风险来源、证据和处置建议将自动进入闭环记录
        </DialogDescription>
      </DialogHeader>

      <div class="flex-1 overflow-y-auto min-h-0 space-y-4 py-4">
        <!-- Risk Selection -->
        <div class="space-y-2">
          <label class="text-label">关联风险事件 *</label>
          <Select :model-value="selectedRiskId" @update:model-value="handleRiskSelect">
            <SelectTrigger class="bg-card/50">
              <SelectValue placeholder="选择风险事件" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="risk in allRisks" :key="risk.id" :value="risk.id">
                <div class="flex items-center gap-2">
                  <span>{{ risk.title }}</span>
                  <Badge :class="`status-badge-${risk.level}`" class="text-[10px]">
                    {{ { high: '高', medium: '中', low: '低', review_required: '复核' }[risk.level] }}
                  </Badge>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <!-- Risk Preview -->
        <div v-if="selectedRisk" class="surface-base card-padding space-y-2">
          <div class="flex items-start justify-between gap-2">
            <div class="flex-1">
              <p class="text-sm font-medium text-foreground">{{ selectedRisk.title }}</p>
              <p class="text-xs text-muted-foreground mt-1">{{ selectedRisk.description }}</p>
            </div>
            <Badge :class="`status-badge-${selectedRisk.level}`">
              {{ { high: '高风险', medium: '中风险', low: '低风险', review_required: '待复核' }[selectedRisk.level] }}
            </Badge>
          </div>
          <p class="text-xs text-muted-foreground">
            触发依据：{{ selectedRisk.evidenceSummary }}
          </p>
          <div v-if="evidenceProfile" class="grid grid-cols-3 gap-2 pt-2">
            <div class="rounded-lg border border-cyan-400/15 bg-cyan-400/[0.05] p-2">
              <div class="text-[10px] text-muted-foreground">AI 置信度</div>
              <strong class="mt-1 block text-sm text-cyan-300">{{ evidenceProfile.confidence }}%</strong>
            </div>
            <div class="rounded-lg border border-border/40 bg-muted/20 p-2">
              <div class="text-[10px] text-muted-foreground">推荐模板</div>
              <strong class="mt-1 block truncate text-xs text-foreground">{{ selectedTemplate }}</strong>
            </div>
            <div class="rounded-lg border border-border/40 bg-muted/20 p-2">
              <div class="text-[10px] text-muted-foreground">处置时限</div>
              <strong class="mt-1 block text-xs text-foreground">{{ evidenceProfile.recommendation.urgency }}</strong>
            </div>
          </div>
        </div>

        <!-- Workorder Title -->
        <div class="space-y-2">
          <label class="text-label">工单标题 *</label>
          <Input
            v-model="workorderTitle"
            placeholder="输入工单标题"
            class="bg-card/50 border-border"
          />
        </div>

        <!-- Workorder Summary -->
        <div class="space-y-2">
          <label class="text-label">AI 建议处置</label>
          <Textarea
            v-model="workorderSummary"
            placeholder="输入处理说明或建议..."
            class="min-h-[80px] bg-card/50 border-border text-xs"
          />
        </div>

        <!-- Assignee -->
        <div class="space-y-2">
          <label class="text-label">责任人 *</label>
          <Select :model-value="selectedAssignee" @update:model-value="(val) => selectedAssignee = val">
            <SelectTrigger class="bg-card/50">
              <SelectValue placeholder="选择责任人" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="user in assigneeOptions" :key="user.id" :value="user.id">
                {{ user.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <DialogFooter class="flex-shrink-0 gap-2 pt-4 border-t border-border/50">
        <Button variant="outline" @click="() => emit('close')">
          取消
        </Button>
        <Button
          :disabled="!canCreate"
          class="gap-2 bg-primary hover:bg-primary-hover text-primary-foreground"
          @click="handleCreate"
        >
          <SafeIcon name="Plus" :size="14" />
          确认生成并进入闭环
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

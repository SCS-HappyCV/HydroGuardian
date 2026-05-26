
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
import type { RiskEventVO } from '@/data/RiskEventService'

const props = defineProps<{
  open: boolean
  prefilledRiskId?: string | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', workorder: any): void
}>()

const selectedRiskId = ref('')
const workorderTitle = ref('')
const workorderSummary = ref('')
const selectedAssignee = ref('')

const allRisks = computed(() => RiskEventService.getAll())
const selectedRisk = computed(() => {
  if (!selectedRiskId.value) return null
  return RiskEventService.getByIdVO(selectedRiskId.value)
})
const assigneeOptions = computed(() => UserService.getAll().map(u => ({ id: u.id, name: u.name })))

const canCreate = computed(() => {
  return selectedRiskId.value && workorderTitle.value.trim() && selectedAssignee.value
})

const handleRiskSelect = (riskId: string) => {
  selectedRiskId.value = riskId
  const risk = RiskEventService.getById(riskId)
  if (risk) {
    workorderTitle.value = `${risk.title}处置工单`
    workorderSummary.value = risk.description
  }
}

const handleCreate = () => {
  if (!canCreate.value) {
    toast.error('请填写必要信息')
    return
  }

  const newWorkorder = {
    id: `wo-${Date.now()}`,
    title: workorderTitle.value,
    riskId: selectedRiskId.value,
    assigneeUserId: selectedAssignee.value,
    reviewerUserId: undefined,
    ruleId: selectedRisk.value?.ruleId || '',
    templateId: selectedRisk.value?.templateId || '',
    status: 'todo' as const,
    dueAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    summary: workorderSummary.value,
  }

  const allWorkorders = WorkorderService.getAll()
  allWorkorders.push(newWorkorder)
  WorkorderService.savePersisted(allWorkorders)

  toast.success('工单创建成功')
  emit('created', newWorkorder)

  selectedRiskId.value = ''
  workorderTitle.value = ''
  workorderSummary.value = ''
  selectedAssignee.value = ''
}

onMounted(() => {
  if (props.prefilledRiskId) {
    handleRiskSelect(props.prefilledRiskId)
  }
})

watch(() => props.open, (newVal) => {
  if (!newVal) {
    selectedRiskId.value = ''
    workorderTitle.value = ''
    workorderSummary.value = ''
    selectedAssignee.value = ''
  }
})
</script>

<template>
  <Dialog :open="open" @update:open="(val) => !val && emit('close')">
    <DialogContent class="max-w-2xl flex flex-col max-h-[80vh]">
      <DialogHeader class="flex-shrink-0">
        <DialogTitle>创建新工单</DialogTitle>
        <DialogDescription>
          从风险事件创建工单，追踪处置进展
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
          <label class="text-label">处理说明</label>
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
          创建工单
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

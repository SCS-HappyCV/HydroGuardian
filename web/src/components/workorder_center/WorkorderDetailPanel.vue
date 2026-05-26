
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import SafeIcon from '@/components/common/SafeIcon.vue'
import WorkorderStatusTimeline from './WorkorderStatusTimeline.vue'
import type { WorkorderVO } from '@/data/WorkorderService'
import * as WorkorderService from '@/data/WorkorderService'
import * as WorkorderTimelineService from '@/data/WorkorderTimelineService'
import * as RiskEventService from '@/data/RiskEventService'
import * as UserService from '@/data/UserService'

const props = defineProps<{
  workorder: WorkorderVO
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'update'): void
}>()

const currentWorkorder = ref(props.workorder)
const timeline = ref(WorkorderTimelineService.queryByOrderId(props.workorder.id))
const riskDetail = computed(() => RiskEventService.getByIdVO(currentWorkorder.value.riskId))
const assigneeOptions = computed(() => UserService.getAll().map(u => ({ id: u.id, name: u.name })))
const reviewerOptions = computed(() => UserService.getAll().map(u => ({ id: u.id, name: u.name })))

const selectedAssignee = ref(currentWorkorder.value.assigneeUserId || '')
const selectedReviewer = ref(currentWorkorder.value.reviewerUserId || '')
const processingNote = ref('')
const showStatusDialog = ref(false)
const newStatus = ref(currentWorkorder.value.status)

const statusOptions = [
  { value: 'todo', label: '待处理' },
  { value: 'doing', label: '处理中' },
  { value: 'review', label: '复核中' },
  { value: 'closed', label: '已关闭' },
]

const canTransitionTo = (targetStatus: string): boolean => {
  const current = currentWorkorder.value.status
  const transitions: Record<string, string[]> = {
    todo: ['doing'],
    doing: ['review', 'todo'],
    review: ['closed', 'doing'],
    closed: [],
  }
  return transitions[current]?.includes(targetStatus) || false
}

const handleAssigneeChange = (userId: string) => {
  selectedAssignee.value = userId
  currentWorkorder.value.assigneeUserId = userId
  currentWorkorder.value.assigneeUserName = UserService.getById(userId)?.name
  WorkorderService.savePersisted(WorkorderService.getAll())
  toast.success('责任人已更新')
  emit('update')
}

const handleStatusChange = () => {
  if (!canTransitionTo(newStatus.value)) {
    toast.error('不允许的状态转换')
    return
  }

  currentWorkorder.value.status = newStatus.value as any
  currentWorkorder.value.updatedAt = new Date().toISOString()
  WorkorderService.savePersisted(WorkorderService.getAll())
  timeline.value = WorkorderTimelineService.queryByOrderId(currentWorkorder.value.id)
  toast.success('工单状态已更新')
  showStatusDialog.value = false
  emit('update')
}

const handleSubmitReview = () => {
  if (currentWorkorder.value.status !== 'doing') {
    toast.error('只有处理中的工单才能提交复核')
    return
  }

  if (!processingNote.value.trim()) {
    toast.error('请填写处理说明')
    return
  }

  currentWorkorder.value.status = 'review'
  currentWorkorder.value.updatedAt = new Date().toISOString()
  currentWorkorder.value.summary = processingNote.value
  WorkorderService.savePersisted(WorkorderService.getAll())
  timeline.value = WorkorderTimelineService.queryByOrderId(currentWorkorder.value.id)
  toast.success('已提交复核申请')
  processingNote.value = ''
  emit('update')
}

const handleNavigateToRisk = () => {
  window.location.href = `./risk-workspace.html?riskId=${currentWorkorder.value.riskId}`
}

const handleNavigateToReview = () => {
  window.location.href = `./workorder-review.html?orderId=${currentWorkorder.value.id}`
}

onMounted(() => {
  currentWorkorder.value = props.workorder
  timeline.value = WorkorderTimelineService.queryByOrderId(props.workorder.id)
})
</script>

<template>
  <Sheet :open="open" @update:open="(val) => !val && emit('close')">
    <SheetContent side="right" class="flex flex-col max-w-2xl max-h-[80vh] overflow-hidden">
      <SheetHeader class="flex-shrink-0">
        <SheetTitle class="text-xl">{{ currentWorkorder.title }}</SheetTitle>
        <SheetDescription>
          <div class="flex items-center gap-2 mt-2">
            <Badge :class="`status-badge-${currentWorkorder.status}`">
              {{ { todo: '待处理', doing: '处理中', review: '复核中', closed: '已关闭' }[currentWorkorder.status] }}
            </Badge>
            <span class="text-xs text-muted-foreground">
              创建于 {{ new Date(currentWorkorder.createdAt).toLocaleDateString('zh-CN') }}
            </span>
          </div>
        </SheetDescription>
      </SheetHeader>

      <div class="flex-1 overflow-y-auto min-h-0 space-y-6 py-4 px-6">
        <!-- Risk Info Section -->
        <div class="space-y-3">
          <h4 class="text-sm font-semibold text-foreground">来源风险</h4>
          <div v-if="riskDetail" class="surface-base card-padding space-y-2">
            <div class="flex items-start justify-between gap-2">
              <div class="flex-1">
                <p class="text-sm font-medium text-foreground">{{ riskDetail.title }}</p>
                <p class="text-xs text-muted-foreground mt-1">{{ riskDetail.description }}</p>
              </div>
              <Badge :class="`status-badge-${riskDetail.level}`">
                {{ { high: '高风险', medium: '中风险', low: '低风险', review_required: '待复核' }[riskDetail.level] }}
              </Badge>
            </div>
            <Button
              variant="ghost"
              size="sm"
              class="w-full justify-start text-primary hover:bg-primary/10 text-xs"
              @click="handleNavigateToRisk"
            >
              <SafeIcon name="ExternalLink" :size="12" class="mr-1" />
              查看风险详情
            </Button>
          </div>
        </div>

        <Separator class="opacity-50" />

        <!-- Responsibility Section -->
        <div class="space-y-3">
          <h4 class="text-sm font-semibold text-foreground">责任分配</h4>
          <div class="space-y-2">
            <div>
              <label class="text-label text-xs mb-1 block">责任人</label>
              <Select :model-value="selectedAssignee" @update:model-value="handleAssigneeChange">
                <SelectTrigger class="h-9 bg-card/50">
                  <SelectValue placeholder="选择责任人" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">未分配</SelectItem>
                  <SelectItem v-for="user in assigneeOptions" :key="user.id" :value="user.id">
                    {{ user.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label class="text-label text-xs mb-1 block">复核人</label>
              <Select :model-value="selectedReviewer" @update:model-value="(val) => selectedReviewer = val">
                <SelectTrigger class="h-9 bg-card/50" disabled>
                  <SelectValue :placeholder="currentWorkorder.reviewerUserName || '待分配'" />
                </SelectTrigger>
              </Select>
            </div>
          </div>
        </div>

        <Separator class="opacity-50" />

        <!-- Processing Section -->
        <div class="space-y-3">
          <h4 class="text-sm font-semibold text-foreground">处理进展</h4>
          <Textarea
            v-model="processingNote"
            placeholder="记录处理过程、发现和建议..."
            class="min-h-[100px] bg-card/50 border-border text-xs"
          />
          <p class="text-xs text-muted-foreground">{{ processingNote.length }}/500 字</p>
        </div>

        <Separator class="opacity-50" />

        <!-- Timeline Section -->
        <div class="space-y-3">
          <h4 class="text-sm font-semibold text-foreground">处理时间线</h4>
          <WorkorderStatusTimeline :timeline="timeline" />
        </div>

        <Separator class="opacity-50" />

        <!-- Status Change Section -->
        <div class="space-y-3">
          <h4 class="text-sm font-semibold text-foreground">状态流转</h4>
          <div class="flex flex-wrap gap-2">
            <Button
              v-for="status in statusOptions"
              :key="status.value"
              variant="outline"
              size="sm"
              :disabled="!canTransitionTo(status.value) || currentWorkorder.status === status.value"
              class="text-xs"
              @click="() => { newStatus = status.value; showStatusDialog = true }"
            >
              {{ status.label }}
            </Button>
          </div>
        </div>
      </div>

      <SheetFooter class="flex-shrink-0 gap-2 pt-4 border-t border-border/50">
        <Button
          v-if="currentWorkorder.status === 'doing'"
          class="gap-2 bg-primary hover:bg-primary-hover text-primary-foreground flex-1"
          @click="handleSubmitReview"
        >
          <SafeIcon name="Send" :size="14" />
          提交复核
        </Button>
        <Button
          v-if="currentWorkorder.status === 'review'"
          class="gap-2 bg-accent hover:bg-accent-hover text-accent-foreground flex-1"
          @click="handleNavigateToReview"
        >
          <SafeIcon name="CheckCircle2" :size="14" />
          进行复核
        </Button>
        <Button
          variant="outline"
          class="flex-1"
          @click="() => emit('close')"
        >
          关闭
        </Button>
      </SheetFooter>
    </SheetContent>
  </Sheet>
</template>

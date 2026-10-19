<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
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
import SafeIcon from '@/components/common/SafeIcon.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AiSourceSummary from '@/components/workorder_detail/AiSourceSummary.vue'
import WorkorderStatusTimeline from './WorkorderStatusTimeline.vue'
import type { WorkorderVO } from '@/data/WorkorderService'
import * as WorkorderService from '@/data/WorkorderService'
import * as WorkorderTimelineService from '@/data/WorkorderTimelineService'
import * as RiskEventService from '@/data/RiskEventService'
import * as WorkorderEvidenceService from '@/data/WorkorderEvidenceService'
import * as WorkorderReviewService from '@/data/WorkorderReviewService'
import * as TaskService from '@/data/TaskService'
import * as UserService from '@/data/UserService'

const props = defineProps<{
  workorder: WorkorderVO
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'update'): void
}>()

const currentWorkorder = ref<WorkorderVO>({ ...props.workorder })
const timeline = ref(WorkorderTimelineService.queryByOrderId(props.workorder.id))
const selectedAssignee = ref(currentWorkorder.value.assigneeUserId || '')
const processingNote = ref('')

const riskDetail = computed(() => RiskEventService.getByIdVO(currentWorkorder.value.riskId))
const sourceTask = computed(() => {
  const taskId = currentWorkorder.value.taskId || riskDetail.value?.taskId
  return taskId ? TaskService.getById(taskId) : null
})
const evidence = computed(() => WorkorderEvidenceService.query({ filter: { orderId: currentWorkorder.value.id } }))
const review = computed(() => WorkorderReviewService.getByOrderIdVO(currentWorkorder.value.id))
const assigneeOptions = computed(() => UserService.getAll().map((user) => ({ id: user.id, name: user.name })))

const statusLabel = computed(() => ({
  todo: '待人工确认',
  doing: '现场处置中',
  review: '等待复核',
  closed: '已闭环',
})[currentWorkorder.value.status])

const deadlineLabel = computed(() => new Date(currentWorkorder.value.dueAt).toLocaleString('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
}))

function reloadTimeline() {
  timeline.value = WorkorderTimelineService.queryByOrderId(currentWorkorder.value.id)
}

function syncWorkorder(next: WorkorderVO) {
  currentWorkorder.value = { ...next }
  selectedAssignee.value = next.assigneeUserId || ''
  processingNote.value = ''
  reloadTimeline()
}

function handleAssigneeChange(userId: string) {
  selectedAssignee.value = userId
  const assigneeName = UserService.getById(userId)?.name
  const updated = WorkorderService.update(currentWorkorder.value.id, { assigneeUserId: userId })
  if (updated) currentWorkorder.value = { ...currentWorkorder.value, ...updated, assigneeUserName: assigneeName }
  toast.success(`责任人已更新为${assigneeName || '现场人员'}`)
  emit('update')
}

function handleStartProcessing() {
  if (!selectedAssignee.value) {
    toast.error('请先选择现场责任人')
    return
  }

  const now = new Date().toISOString()
  const assigneeName = UserService.getById(selectedAssignee.value)?.name
  const updated = WorkorderService.update(currentWorkorder.value.id, { status: 'doing', updatedAt: now })
  if (updated) currentWorkorder.value = { ...currentWorkorder.value, ...updated }
  WorkorderTimelineService.appendEvent({
    id: `wot-${Date.now()}`,
    orderId: currentWorkorder.value.id,
    actorUserId: selectedAssignee.value,
    action: 'processing',
    note: `人工确认风险，已派发${assigneeName || '现场责任人'}开展处置。`,
    createdAt: now,
  })
  reloadTimeline()
  toast.success('已确认风险并派发现场处置')
  emit('update')
}

function handleSubmitReview() {
  if (!processingNote.value.trim()) {
    toast.error('请先填写现场处理说明')
    return
  }

  const now = new Date().toISOString()
  const updated = WorkorderService.update(currentWorkorder.value.id, {
    status: 'review',
    summary: processingNote.value,
    updatedAt: now,
  })
  if (updated) currentWorkorder.value = { ...currentWorkorder.value, ...updated }
  WorkorderTimelineService.appendEvent({
    id: `wot-${Date.now()}`,
    orderId: currentWorkorder.value.id,
    actorUserId: currentWorkorder.value.assigneeUserId || 'user-002',
    action: 'review_requested',
    note: processingNote.value,
    createdAt: now,
  })
  reloadTimeline()
  processingNote.value = ''
  toast.success('现场反馈已提交复核')
  emit('update')
}

function handleNavigateToRisk() {
  window.location.href = `./risk-workspace.html?riskId=${encodeURIComponent(currentWorkorder.value.riskId)}`
}

function handleNavigateToReview() {
  window.location.href = `./workorder-review.html?orderId=${encodeURIComponent(currentWorkorder.value.id)}`
}

function handleNavigateToDetail() {
  window.location.href = `./workorder-detail.html?orderId=${encodeURIComponent(currentWorkorder.value.id)}`
}

watch(() => props.workorder, syncWorkorder)
</script>

<template>
  <Sheet :open="open" @update:open="(value) => !value && emit('close')">
    <SheetContent
      side="right"
      class="h-dvh max-h-none w-full max-w-none gap-0 overflow-hidden border-l border-cyan-400/15 bg-[#07111f] p-0 sm:max-w-[760px]"
    >
      <SheetHeader class="shrink-0 border-b border-white/10 bg-[#091725]/95 px-6 py-4 pr-14">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="mb-1.5 flex items-center gap-2">
              <span class="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-300">CLOSURE DETAIL</span>
              <StatusBadge :status="currentWorkorder.status" size="sm" />
            </div>
            <SheetTitle class="truncate text-lg text-white">{{ currentWorkorder.title }}</SheetTitle>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ currentWorkorder.id }} · {{ statusLabel }}
            </p>
          </div>
          <div class="grid grid-cols-2 gap-2 text-right">
            <div class="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
              <div class="text-[9px] text-slate-500">现场责任人</div>
              <div class="mt-0.5 text-xs font-medium text-slate-200">{{ currentWorkorder.assigneeUserName || '待分配' }}</div>
            </div>
            <div class="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
              <div class="text-[9px] text-slate-500">处置时限</div>
              <div class="mt-0.5 text-xs font-medium text-slate-200">{{ deadlineLabel }}</div>
            </div>
          </div>
        </div>
      </SheetHeader>

      <div class="min-h-0 flex-1 overflow-y-auto">
        <div class="space-y-4 p-4 sm:p-5">
          <AiSourceSummary
            :workorder="currentWorkorder"
            :risk="riskDetail"
            :task="sourceTask"
            :evidence="evidence"
            compact
          />

          <div class="grid gap-4" :class="currentWorkorder.status === 'closed' ? 'grid-cols-1' : 'lg:grid-cols-[230px_1fr]'">
            <section v-if="currentWorkorder.status !== 'closed'" class="space-y-4 rounded-2xl border border-white/10 bg-white/[0.025] p-4">
              <div>
                <h3 class="flex items-center gap-2 text-xs font-semibold text-white">
                  <SafeIcon name="UsersRound" :size="14" class="text-cyan-300" />
                  责任与现场反馈
                </h3>
                <p class="mt-1 text-[10px] text-slate-500">完成当前阶段所需的最少信息</p>
              </div>

              <div class="space-y-1.5">
                <label class="text-[10px] text-slate-400">现场责任人</label>
                <Select :model-value="selectedAssignee" @update:model-value="handleAssigneeChange">
                  <SelectTrigger class="h-9 border-white/10 bg-black/20 text-xs">
                    <SelectValue placeholder="选择责任人" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="user in assigneeOptions" :key="user.id" :value="user.id">
                      {{ user.name }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div v-if="currentWorkorder.status === 'doing'" class="space-y-1.5">
                <label class="text-[10px] text-slate-400">现场处理说明</label>
                <Textarea
                  v-model="processingNote"
                  placeholder="记录现场措施、处理结果和回传证据…"
                  class="min-h-[128px] resize-none border-white/10 bg-black/20 text-xs"
                  maxlength="500"
                />
                <p class="text-right text-[9px] text-slate-500">{{ processingNote.length }}/500</p>
              </div>

              <div v-if="currentWorkorder.status === 'review'" class="rounded-xl border border-violet-300/15 bg-violet-300/[0.05] p-3">
                <div class="flex items-center gap-2 text-xs font-medium text-violet-200">
                  <SafeIcon name="ClipboardCheck" :size="14" />
                  已进入人工复核
                </div>
                <p class="mt-2 text-[10px] leading-relaxed text-slate-400">现场反馈已锁定，请由复核人确认处置效果和证据完整性。</p>
              </div>
            </section>

            <WorkorderStatusTimeline
              :workorder="currentWorkorder"
              :timeline="timeline"
              :evidence="evidence"
              :review="review"
            />
          </div>
        </div>
      </div>

      <SheetFooter class="shrink-0 flex-row items-center justify-between gap-2 border-t border-white/10 bg-[#091725] px-5 py-3 sm:justify-between">
        <div class="flex gap-2">
          <Button variant="ghost" size="sm" class="gap-1.5 text-slate-300" @click="handleNavigateToRisk">
            <SafeIcon name="MapPinned" :size="14" />
            风险证据
          </Button>
          <Button variant="outline" size="sm" class="gap-1.5 border-white/10" @click="handleNavigateToDetail">
            <SafeIcon name="Maximize2" :size="14" />
            完整详情
          </Button>
        </div>

        <Button
          v-if="currentWorkorder.status === 'todo'"
          size="sm"
          class="gap-1.5"
          @click="handleStartProcessing"
        >
          <SafeIcon name="Send" :size="14" />
          确认并派发处置
        </Button>
        <Button
          v-else-if="currentWorkorder.status === 'doing'"
          size="sm"
          class="gap-1.5"
          @click="handleSubmitReview"
        >
          <SafeIcon name="UploadCloud" :size="14" />
          提交现场反馈
        </Button>
        <Button
          v-else-if="currentWorkorder.status === 'review'"
          size="sm"
          class="gap-1.5 bg-violet-500 hover:bg-violet-400"
          @click="handleNavigateToReview"
        >
          <SafeIcon name="UserRoundCheck" :size="14" />
          进入人工复核
        </Button>
        <div v-else class="flex items-center gap-2 rounded-lg border border-emerald-300/15 bg-emerald-300/[0.06] px-3 py-2 text-xs font-medium text-emerald-300">
          <SafeIcon name="BadgeCheck" :size="15" />
          处置闭环已完成
        </div>
      </SheetFooter>
    </SheetContent>
  </Sheet>
</template>

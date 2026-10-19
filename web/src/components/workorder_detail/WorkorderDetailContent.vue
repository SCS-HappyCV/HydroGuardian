
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import SafeIcon from '@/components/common/SafeIcon.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AiSourceSummary from './AiSourceSummary.vue'
import WorkorderTimelineSection from './WorkorderTimelineSection.vue'
import WorkorderReviewDialog from './WorkorderReviewDialog.vue'
import AttachmentUploadZone from './AttachmentUploadZone.vue'
import RemoteEvidenceGallery from './RemoteEvidenceGallery.vue'
import FieldLocationPanel from '@/components/common/FieldLocationPanel.vue'
import { getById as getWorkorderById, update as updateWorkorder } from '@/data/WorkorderService'
import { appendEvent, queryByOrderId as getTimelineByOrderId } from '@/data/WorkorderTimelineService'
import { getByOrderIdVO as getReviewByOrderId } from '@/data/WorkorderReviewService'
import { getById as getRiskById } from '@/data/RiskEventService'
import { getById as getTaskById } from '@/data/TaskService'
import { getAll as getAllEvidence, query as queryEvidence, savePersisted as saveEvidence } from '@/data/WorkorderEvidenceService'
import { getAll as getAllUsers } from '@/data/UserService'
import { getAgentWorkorderContext } from '@/lib/agent-workorder-context'
import type { WorkorderVO } from '@/data/WorkorderService'
import type { WorkorderTimelineVO } from '@/data/WorkorderTimelineService'
import type { WorkorderReviewVO } from '@/data/WorkorderReviewService'
import { remoteAgentApi } from '@/api/remote-agent-api'
import type { RemoteWorkorder } from '@/lib/remote-workorder-types'
import { mapRemoteEvidence, mapRemoteReview, mapRemoteRisk, mapRemoteTimeline, mapRemoteWorkorder } from '@/lib/remote-workorder-mapper'

const isClient = ref(true)
const currentOrderId = ref('wo-2001')
const workorder = ref<WorkorderVO | null>(null)
const timeline = ref<WorkorderTimelineVO[]>([])
const review = ref<WorkorderReviewVO | null>(null)
const risk = ref<any>(null)
const sourceTask = ref<any>(null)
const evidence = ref<any[]>([])
const users = ref(getAllUsers())
const remoteOrder = ref<RemoteWorkorder | null>(null)

const processingNote = ref('')
const selectedAssignee = ref<string | undefined>()
const showReviewDialog = ref(false)
const attachments = ref<File[]>([])

const statusFlow = {
  todo: ['doing'],
  doing: ['review'],
  review: [],
  closed: []
}

const canTransitionTo = computed(() => {
  if (!workorder.value) return []
  return statusFlow[workorder.value.status as keyof typeof statusFlow] || []
})

const statusLabels: Record<string, string> = {
  todo: '待处理',
  doing: '处理中',
  review: '复核中',
  closed: '已关闭'
}

const applyRemoteOrder = (order: RemoteWorkorder) => {
  remoteOrder.value = order
  workorder.value = mapRemoteWorkorder(order)
  selectedAssignee.value = order.assignee_user_id || undefined
  timeline.value = mapRemoteTimeline(order)
  review.value = mapRemoteReview(order)
  risk.value = mapRemoteRisk(order)
  sourceTask.value = getTaskById(order.task_id || '')
  evidence.value = mapRemoteEvidence(order)
}

const loadWorkorderData = async () => {
  if (currentOrderId.value.startsWith('wo_')) {
    try {
      applyRemoteOrder(await remoteAgentApi.getWorkorder(currentOrderId.value))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '工单同步失败')
    }
    return
  }
  const wo = getWorkorderById(currentOrderId.value)
  if (wo) {
    workorder.value = wo
    selectedAssignee.value = wo.assigneeUserId
    timeline.value = getTimelineByOrderId(currentOrderId.value)
    review.value = getReviewByOrderId(currentOrderId.value)
    const agentContext = getAgentWorkorderContext(wo)
    risk.value = agentContext?.risk || getRiskById(wo.riskId)
    sourceTask.value = getTaskById(wo.taskId || risk.value?.taskId)
    const storedEvidence = queryEvidence({ filter: { orderId: currentOrderId.value } })
    evidence.value = [...(agentContext?.evidence || []), ...storedEvidence]
  }
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    const params = new URLSearchParams(window.location.search)
    const orderId = params.get('orderId')
    if (orderId) currentOrderId.value = orderId
    loadWorkorderData().finally(() => { isClient.value = true })
  })
})

const handleStatusTransition = async (newStatus: string) => {
  if (!workorder.value) return
  
  if (newStatus === 'doing' && !selectedAssignee.value) {
    toast.error('请先分配责任人')
    return
  }

  if (newStatus === 'review' && !processingNote.value.trim()) {
    toast.error('请填写处理说明')
    return
  }

  if (remoteOrder.value) {
    try {
      if (newStatus === 'doing') {
        applyRemoteOrder(await remoteAgentApi.startWorkorder(remoteOrder.value.workorder_id, { actor_user_id: selectedAssignee.value }))
      } else if (newStatus === 'review') {
        const uploaded = []
        for (const file of attachments.value) {
          const presigned = await remoteAgentApi.presignUpload({ filename: file.name, media_type: file.type || 'application/octet-stream', job_id: remoteOrder.value.job_id })
          await remoteAgentApi.uploadFile(presigned.upload_url, file)
          await remoteAgentApi.completeUpload(presigned.artifact.artifact_id, { workorder_id: remoteOrder.value.workorder_id, evidence_type: 'after' })
          uploaded.push({ artifact_id: presigned.artifact.artifact_id, title: file.name })
        }
        applyRemoteOrder(await remoteAgentApi.submitWorkorderFeedback(remoteOrder.value.workorder_id, { actor_user_id: selectedAssignee.value, note: processingNote.value, evidence: uploaded }))
      }
      toast.success(`工单状态已更新为"${statusLabels[newStatus]}"`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '工单状态更新失败')
    }
    return
  }

  const now = new Date().toISOString()
  const updated = updateWorkorder(workorder.value.id, {
    status: newStatus as any,
    summary: newStatus === 'review' ? processingNote.value : workorder.value.summary,
    updatedAt: now,
  })
  if (updated) workorder.value = { ...workorder.value, ...updated }

  if (newStatus === 'review') {
    const generatedEvidence = [
      {
        id: `evi-note-${Date.now()}`,
        orderId: workorder.value.id,
        evidenceType: 'after' as const,
        title: '现场核查与处置说明',
        content: processingNote.value,
        createdAt: now,
      },
      ...attachments.value.map((file, index) => ({
        id: `evi-file-${Date.now()}-${index}`,
        orderId: workorder.value!.id,
        evidenceType: 'after' as const,
        title: file.name,
        content: '现场人员提交的定位照片或处置材料。',
        createdAt: now,
      })),
    ]
    saveEvidence([...getAllEvidence().filter((item) => item.orderId !== workorder.value?.id || item.evidenceType !== 'after'), ...generatedEvidence])
    evidence.value = queryEvidence({ filter: { orderId: workorder.value.id } })
  }

  const action = newStatus === 'doing' ? 'processing' : newStatus === 'review' ? 'review_requested' : 'closed'
  appendEvent({
    id: `wot-${Date.now()}`,
    orderId: workorder.value.id,
    actorUserId: selectedAssignee.value || workorder.value.reviewerUserId || 'user-001',
    action,
    note: newStatus === 'doing'
      ? '现场处置任务已启动。'
      : newStatus === 'review'
        ? processingNote.value
        : '人工复核通过，工单闭环关闭。',
    createdAt: now,
  })
  timeline.value = getTimelineByOrderId(workorder.value.id)
  toast.success(`工单状态已更新为"${statusLabels[newStatus]}"`)
}

const handleAssigneeChange = async (userId: string) => {
  if (!workorder.value) return
  
  selectedAssignee.value = userId
  if (remoteOrder.value) {
    try {
      applyRemoteOrder(await remoteAgentApi.assignWorkorder(remoteOrder.value.workorder_id, { assignee_user_id: userId, actor_user_id: userId }))
      toast.success('责任人已更新')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '责任人更新失败')
    }
    return
  }
  const now = new Date().toISOString()
  const updated = updateWorkorder(workorder.value.id, { assigneeUserId: userId, updatedAt: now })
  if (updated) workorder.value = { ...workorder.value, ...updated }
  appendEvent({
    id: `wot-${Date.now()}`,
    orderId: workorder.value.id,
    actorUserId: userId,
    action: 'assigned',
    note: '人工确认风险并完成现场责任人指派。',
    createdAt: now,
  })
  timeline.value = getTimelineByOrderId(workorder.value.id)
  toast.success('责任人已更新')
}

const handleReviewSubmit = (decision: 'approved' | 'rejected', comment: string) => {
  if (!workorder.value) return
  
  if (decision === 'approved') {
    handleStatusTransition('closed')
  }
  
  showReviewDialog.value = false
  toast.success(`复核结果已提交：${decision === 'approved' ? '通过' : '驳回'}`)
}

const handleOpenReview = () => {
  if (!workorder.value) return
  window.location.href = `./workorder-review.html?orderId=${encodeURIComponent(workorder.value.id)}`
}

const handleAttachmentAdd = (file: File) => {
  attachments.value.push(file)
  toast.success(`已添加附件：${file.name}`)
}

const handleAttachmentRemove = (index: number) => {
  attachments.value.splice(index, 1)
  toast.info('附件已移除')
}

const handleBackToCenter = () => {
  window.location.href = './workorder-center.html'
}

const handleViewRisk = () => {
  if (workorder.value?.riskId) {
    const params = new URLSearchParams({ riskId: workorder.value.riskId })
    if (workorder.value.taskId) params.set('taskId', workorder.value.taskId)
    window.location.href = `./risk-workspace.html?${params.toString()}`
  }
}

const handleOpenAuditReport = () => {
  if (remoteOrder.value) window.location.href = `./audit-report.html?jobId=${encodeURIComponent(remoteOrder.value.job_id)}&workorderId=${encodeURIComponent(remoteOrder.value.workorder_id)}`
}
</script>

<template>
  <div v-if="isClient && workorder" class="flex flex-col h-full min-h-0 bg-background">
    <PageHeader 
      :title="`工单 ${workorder.id}`"
      :subtitle="workorder.title"
      :breadcrumb="[
        { label: '全局总览', href: './dashboard.html' },
        { label: '工单中心', href: './workorder-center.html' },
        { label: workorder.id }
      ]"
    >
      <template #actions>
        <Button v-if="remoteOrder" variant="outline" size="sm" class="gap-2" @click="handleOpenAuditReport">
          <SafeIcon name="FileCheck2" :size="16" />审计报告
        </Button>
        <Button 
          variant="outline" 
          size="sm"
          @click="handleBackToCenter"
          class="gap-2"
        >
          <SafeIcon name="ArrowLeft" :size="16" />
          返回
        </Button>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0 page-body">
      <div class="mx-auto max-w-7xl space-y-6">
        <section class="grid grid-cols-4 overflow-hidden rounded-2xl border border-border/60 bg-card/40">
          <div v-for="(stage, index) in [{ label: '待接收', icon: 'Inbox' }, { label: '现场核查', icon: 'MapPinCheck' }, { label: '人工复核', icon: 'UserRoundCheck' }, { label: '闭环完成', icon: 'BadgeCheck' }]" :key="stage.label" class="relative flex items-center gap-3 border-r border-border/40 p-4 last:border-r-0" :class="index <= ({ todo: 0, doing: 1, review: 2, closed: 3 }[workorder.status] ?? 0) ? 'bg-primary/[0.07]' : 'opacity-45'"><span class="grid h-8 w-8 place-items-center rounded-full" :class="index <= ({ todo: 0, doing: 1, review: 2, closed: 3 }[workorder.status] ?? 0) ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'"><SafeIcon :name="stage.icon" :size="15" /></span><div><p class="text-[10px] text-muted-foreground">阶段 {{ index + 1 }}</p><p class="text-xs font-medium">{{ stage.label }}</p></div></div>
        </section>
        <AiSourceSummary
          :workorder="workorder"
          :risk="risk"
          :task="sourceTask"
          :evidence="evidence"
        />
        <RemoteEvidenceGallery v-if="remoteOrder" :evidence="remoteOrder.evidence" />
        <FieldLocationPanel
          :location="workorder.location || risk?.location"
          :label="workorder.title"
          title="现场核查位置"
        />

        <!-- 工单基本信息 -->
        <Card class="surface-base border-border/50">
          <CardHeader class="pb-4">
            <div class="flex items-center justify-between">
              <div class="space-y-1">
                <CardTitle class="text-xl">工单信息</CardTitle>
                <CardDescription>基本属性与状态</CardDescription>
              </div>
              <StatusBadge :status="workorder.status" size="lg" />
            </div>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="space-y-2">
                <label class="text-label">工单ID</label>
                <div class="text-sm text-foreground font-mono bg-muted/20 p-2 rounded border border-border/30">
                  {{ workorder.id }}
                </div>
              </div>
              
              <div class="space-y-2">
                <label class="text-label">创建时间</label>
                <div class="text-sm text-foreground">
                  {{ new Date(workorder.createdAt).toLocaleString('zh-CN') }}
                </div>
              </div>

              <div class="space-y-2">
                <label class="text-label">截止时间</label>
                <div class="text-sm text-foreground">
                  {{ new Date(workorder.dueAt).toLocaleString('zh-CN') }}
                </div>
              </div>

              <div class="space-y-2">
                <label class="text-label">优先级</label>
                <Badge variant="outline" class="w-fit">
                  <SafeIcon name="AlertCircle" :size="12" class="mr-1" />
                  高
                </Badge>
              </div>
            </div>

            <Separator class="opacity-30" />

            <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/40 bg-muted/15 p-3">
              <div>
                <div class="text-xs font-medium text-foreground">来源关系已锁定</div>
                <div class="mt-1 text-[11px] text-muted-foreground">
                  任务 {{ workorder.taskId || risk?.taskId || '-' }} · 风险 {{ workorder.riskId }} · Case {{ workorder.caseId || risk?.caseId || '-' }}
                </div>
              </div>
              <Button variant="outline" size="sm" class="gap-1.5" @click="handleViewRisk">
                <SafeIcon name="ExternalLink" :size="13" />
                返回风险证据
              </Button>
            </div>
          </CardContent>
        </Card>

        <!-- 工单处理 -->
        <Tabs defaultValue="processing" class="w-full">
          <TabsList class="grid w-full grid-cols-3 bg-muted/30">
            <TabsTrigger value="processing">处理进度</TabsTrigger>
            <TabsTrigger value="timeline">处理时间线</TabsTrigger>
            <TabsTrigger value="review">复核记录</TabsTrigger>
          </TabsList>

          <!-- 处理进度标签页 -->
          <TabsContent value="processing" class="space-y-4">
            <Card class="surface-base border-border/50">
              <CardHeader>
                <CardTitle class="text-lg">处理信息</CardTitle>
              </CardHeader>
              <CardContent class="space-y-4">
                <!-- 责任人分配 -->
                <div class="space-y-2">
                  <label class="text-label">责任人</label>
                  <div class="flex gap-2">
                    <select 
                      :value="selectedAssignee || ''"
                      @change="(e) => handleAssigneeChange((e.target as HTMLSelectElement).value)"
                      class="flex-1 px-3 py-2 bg-card/50 border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      <option value="">选择责任人</option>
                      <option v-for="user in users" :key="user.id" :value="user.id">
                        {{ user.name }} ({{ user.email }})
                      </option>
                    </select>
                  </div>
                  <p v-if="workorder.assigneeUserName" class="text-xs text-muted-foreground">
                    当前责任人：{{ workorder.assigneeUserName }}
                  </p>
                </div>

                <Separator class="opacity-30" />

                <!-- 处理说明 -->
                <div class="space-y-2">
                  <label class="text-label">处理说明</label>
                  <textarea 
                    v-model="processingNote"
                    placeholder="请详细描述处理过程、采取的措施及结果..."
                    class="w-full px-3 py-2 bg-card/50 border border-border rounded-md text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-none"
                    rows="6"
                  />
                  <p class="text-xs text-muted-foreground">{{ processingNote.length }} / 2000 字符</p>
                </div>

                <Separator class="opacity-30" />

                <!-- 附件上传 -->
                <div class="space-y-2">
                  <label class="text-label">处理附件</label>
                  <AttachmentUploadZone 
                    :attachments="attachments"
                    @add="handleAttachmentAdd"
                    @remove="handleAttachmentRemove"
                  />
                </div>

                <Separator class="opacity-30" />

                <!-- 状态流转按钮 -->
                <div class="flex gap-2 pt-2">
                  <Button 
                    v-for="nextStatus in canTransitionTo"
                    :key="nextStatus"
                    @click="handleStatusTransition(nextStatus)"
                    class="flex-1 gap-2"
                    :variant="nextStatus === 'review' ? 'default' : 'outline'"
                  >
                    <SafeIcon 
                      :name="nextStatus === 'doing' ? 'Play' : nextStatus === 'review' ? 'CheckCircle2' : 'Archive'"
                      :size="16"
                    />
                    {{ nextStatus === 'doing' ? '开始处理' : nextStatus === 'review' ? '申请复核' : '关闭工单' }}
                  </Button>
                  <Button v-if="workorder.status === 'review'" class="flex-1 gap-2" @click="handleOpenReview"><SafeIcon name="UserRoundCheck" :size="16" />进入人工复核</Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <!-- 处理时间线标签页 -->
          <TabsContent value="timeline">
            <WorkorderTimelineSection
              :workorder="workorder"
              :timeline="timeline"
              :evidence="evidence"
              :review="review"
            />
          </TabsContent>

          <!-- 复核记录标签页 -->
          <TabsContent value="review" class="space-y-4">
            <Card class="surface-base border-border/50">
              <CardHeader>
                <CardTitle class="text-lg">复核信息</CardTitle>
              </CardHeader>
              <CardContent>
                <div v-if="review" class="space-y-4">
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="space-y-2">
                      <label class="text-label">复核人</label>
                      <div class="text-sm text-foreground">{{ review.reviewerUserName }}</div>
                    </div>
                    <div class="space-y-2">
                      <label class="text-label">复核结果</label>
                      <Badge :variant="review.decision === 'approved' ? 'default' : 'destructive'">
                        {{ review.decision === 'approved' ? '通过' : '驳回' }}
                      </Badge>
                    </div>
                  </div>
                  <Separator class="opacity-30" />
                  <div class="space-y-2">
                    <label class="text-label">复核意见</label>
                    <div class="bg-muted/20 border border-border/30 rounded p-3 text-sm text-foreground">
                      {{ review.comment }}
                    </div>
                  </div>
                  <div class="space-y-2">
                    <label class="text-label">证据说明</label>
                    <div class="bg-muted/20 border border-border/30 rounded p-3 text-sm text-foreground">
                      {{ review.evidenceNote }}
                    </div>
                  </div>
                </div>
                <div v-else class="text-center py-8 text-muted-foreground">
                  <SafeIcon name="Inbox" :size="32" class="mx-auto mb-2 opacity-20" />
                  <p class="text-sm">暂无复核记录</p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>

    <!-- 复核对话框 -->
    <WorkorderReviewDialog 
      v-if="showReviewDialog"
      :order-id="workorder.id"
      @submit="handleReviewSubmit"
      @cancel="showReviewDialog = false"
    />
  </div>

  <!-- 加载状态 -->
  <div v-else class="flex items-center justify-center h-full">
    <div class="text-center space-y-4">
      <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin mx-auto" />
      <p class="text-muted-foreground">加载工单详情中...</p>
    </div>
  </div>
</template>

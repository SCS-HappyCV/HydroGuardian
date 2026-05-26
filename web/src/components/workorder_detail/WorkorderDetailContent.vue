
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
import WorkorderTimelineSection from './WorkorderTimelineSection.vue'
import WorkorderReviewDialog from './WorkorderReviewDialog.vue'
import AttachmentUploadZone from './AttachmentUploadZone.vue'
import { getById as getWorkorderById, savePersisted as saveWorkorder } from '@/data/WorkorderService'
import { queryByOrderId as getTimelineByOrderId } from '@/data/WorkorderTimelineService'
import { getByOrderIdVO as getReviewByOrderId } from '@/data/WorkorderReviewService'
import { getById as getRiskById } from '@/data/RiskEventService'
import { getAll as getAllUsers } from '@/data/UserService'
import type { WorkorderVO } from '@/data/WorkorderService'
import type { WorkorderTimelineVO } from '@/data/WorkorderTimelineService'
import type { WorkorderReviewVO } from '@/data/WorkorderReviewService'

const isClient = ref(true)
const currentOrderId = ref('wo-2001')
const workorder = ref<WorkorderVO | null>(null)
const timeline = ref<WorkorderTimelineVO[]>([])
const review = ref<WorkorderReviewVO | null>(null)
const risk = ref<any>(null)
const users = ref(getAllUsers())

const processingNote = ref('')
const selectedAssignee = ref<string | undefined>()
const showReviewDialog = ref(false)
const attachments = ref<File[]>([])

const statusFlow = {
  todo: ['doing'],
  doing: ['review'],
  review: ['closed'],
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

const loadWorkorderData = () => {
  const wo = getWorkorderById(currentOrderId.value)
  if (wo) {
    workorder.value = wo
    selectedAssignee.value = wo.assigneeUserId
    timeline.value = getTimelineByOrderId(currentOrderId.value)
    review.value = getReviewByOrderId(currentOrderId.value)
    risk.value = getRiskById(wo.riskId)
  }
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    const params = new URLSearchParams(window.location.search)
    const orderId = params.get('orderId')
    if (orderId) {
      currentOrderId.value = orderId
      loadWorkorderData()
    }
    isClient.value = true
  })
})

const handleStatusTransition = (newStatus: string) => {
  if (!workorder.value) return
  
  if (newStatus === 'doing' && !selectedAssignee.value) {
    toast.error('请先分配责任人')
    return
  }

  if (newStatus === 'review' && !processingNote.value.trim()) {
    toast.error('请填写处理说明')
    return
  }

  const updatedWorkorders = [
    ...require('@/data/WorkorderService').workorderDataList.map((w: any) => 
      w.id === workorder.value!.id 
        ? { ...w, status: newStatus, updatedAt: new Date().toISOString() }
        : w
    )
  ]
  saveWorkorder(updatedWorkorders)
  
  workorder.value = { ...workorder.value, status: newStatus as any }
  toast.success(`工单状态已更新为"${statusLabels[newStatus]}"`)
}

const handleAssigneeChange = (userId: string) => {
  if (!workorder.value) return
  
  selectedAssignee.value = userId
  const updatedWorkorders = [
    ...require('@/data/WorkorderService').workorderDataList.map((w: any) =>
      w.id === workorder.value!.id
        ? { ...w, assigneeUserId: userId, updatedAt: new Date().toISOString() }
        : w
    )
  ]
  saveWorkorder(updatedWorkorders)
  workorder.value = { ...workorder.value, assigneeUserId: userId }
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
    window.location.href = `./risk-workspace.html?riskId=${workorder.value.riskId}`
  }
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
      <div class="space-y-6 max-w-6xl">
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

            <!-- 来源风险信息 -->
            <div class="space-y-3">
              <h4 class="text-sm font-semibold text-foreground">来源风险</h4>
              <div class="bg-muted/20 border border-border/30 rounded p-3 space-y-2">
                <div class="flex items-start justify-between gap-2">
                  <div class="flex-1">
                    <p class="text-sm font-medium text-foreground">{{ risk?.title || '风险点' }}</p>
                    <p class="text-xs text-muted-foreground mt-1">{{ risk?.description }}</p>
                  </div>
                  <StatusBadge :status="risk?.level || 'high'" size="sm" />
                </div>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  class="text-primary hover:text-primary-hover gap-1 px-0"
                  @click="handleViewRisk"
                >
                  <SafeIcon name="ExternalLink" :size="14" />
                  查看风险详情
                </Button>
              </div>
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
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <!-- 处理时间线标签页 -->
          <TabsContent value="timeline">
            <WorkorderTimelineSection :timeline="timeline" />
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

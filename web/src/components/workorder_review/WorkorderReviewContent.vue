
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Label } from '@/components/ui/label'
import SafeIcon from '@/components/common/SafeIcon.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import FieldLocationPanel from '@/components/common/FieldLocationPanel.vue'
import { toast } from 'vue-sonner'
import type { WorkorderVO } from '@/data/WorkorderService'
import type { WorkorderReviewData } from '@/data/WorkorderReviewData'
import type { RiskEventData } from '@/data/RiskEventData'
import { getByIdVO as getWorkorderByIdVO, update as updateWorkorder } from '@/data/WorkorderService'
import { getByOrderIdVO as getReviewByOrderIdVO, getAll as getAllReviews, savePersisted as saveReviews } from '@/data/WorkorderReviewService'
import { getById as getRiskById } from '@/data/RiskEventService'
import { getById as getUserById } from '@/data/UserService'
import { appendEvent } from '@/data/WorkorderTimelineService'
import { getAgentWorkorderContext } from '@/lib/agent-workorder-context'
import { remoteAgentApi } from '@/api/remote-agent-api'
import type { RemoteWorkorder } from '@/lib/remote-workorder-types'
import { mapRemoteReview, mapRemoteRisk, mapRemoteWorkorder } from '@/lib/remote-workorder-mapper'

const isClient = ref(true)
const orderId = ref<string>('wo-2002')
const workorder = ref<WorkorderVO | null>(null)
const risk = ref<RiskEventData | null>(null)
const existingReview = ref<WorkorderReviewData | null>(null)
const decision = ref<'approved' | 'rejected'>('approved')
const comment = ref<string>('')
const evidenceNote = ref<string>('')
const isSubmitting = ref(false)
const remoteOrder = ref<RemoteWorkorder | null>(null)

const breadcrumbItems = computed(() => [
  { label: '工单中心', href: './workorder-center.html' },
  { label: workorder.value?.title || '工单复核', href: '' }
])

const reviewerName = computed(() => {
  if (workorder.value?.reviewerUserId) {
    return getUserById(workorder.value.reviewerUserId)?.name || '未知用户'
  }
  return '系统管理员'
})

const riskLevelColor = computed(() => {
  if (!risk.value) return 'primary'
  const levelMap: Record<string, 'primary' | 'accent' | 'success' | 'warning' | 'destructive'> = {
    high: 'destructive',
    medium: 'warning',
    low: 'success',
    review_required: 'accent'
  }
  return levelMap[risk.value.level] || 'primary'
})

const loadData = async () => {
  const params = new URLSearchParams(window.location.search)
  const paramOrderId = params.get('orderId')
  
  if (paramOrderId) {
    orderId.value = paramOrderId
  }

  if (orderId.value.startsWith('wo_')) {
    try {
      const order = await remoteAgentApi.getWorkorder(orderId.value)
      remoteOrder.value = order
      workorder.value = mapRemoteWorkorder(order)
      risk.value = mapRemoteRisk(order)
      const review = mapRemoteReview(order)
      if (review) {
        existingReview.value = review
        decision.value = review.decision
        comment.value = review.comment
        evidenceNote.value = review.evidenceNote
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '复核工单同步失败')
    }
    return
  }

  const wo = getWorkorderByIdVO(orderId.value)
  if (wo) {
    workorder.value = wo
    risk.value = getAgentWorkorderContext(wo)?.risk || getRiskById(wo.riskId) || null
    
    const review = getReviewByOrderIdVO(orderId.value)
    if (review) {
      existingReview.value = review
      decision.value = review.decision
      comment.value = review.comment
      evidenceNote.value = review.evidenceNote
    } else {
      const draft = localStorage.getItem(`workorder_review_draft_${orderId.value}`)
      if (draft) {
        try {
          const parsed = JSON.parse(draft)
          comment.value = parsed.comment || ''
          evidenceNote.value = parsed.evidenceNote || ''
        } catch (e) {
          console.error('Failed to parse draft:', e)
        }
      }
    }
  }
}

const saveDraft = () => {
  const draft = {
    comment: comment.value,
    evidenceNote: evidenceNote.value
  }
  localStorage.setItem(`workorder_review_draft_${orderId.value}`, JSON.stringify(draft))
}

const handleCommentChange = () => {
  saveDraft()
}

const handleEvidenceNoteChange = () => {
  saveDraft()
}

const handleSubmit = async () => {
  if (!comment.value.trim()) {
    toast.error('请填写复核意见')
    return
  }

  if (!evidenceNote.value.trim()) {
    toast.error('请填写证据说明')
    return
  }

  isSubmitting.value = true

  try {
    if (remoteOrder.value) {
      await remoteAgentApi.reviewWorkorder(remoteOrder.value.workorder_id, {
        reviewer_user_id: remoteOrder.value.reviewer_user_id || 'user-004',
        decision: decision.value,
        comment: comment.value,
        evidence_note: evidenceNote.value,
      })
      localStorage.removeItem(`workorder_review_draft_${orderId.value}`)
      toast.success(decision.value === 'approved' ? '复核已通过，工单已完成闭环' : '复核已驳回，工单返回现场核查')
      window.setTimeout(() => { window.location.href = `./workorder-detail.html?orderId=${encodeURIComponent(orderId.value)}` }, 600)
      return
    }
    const reviewData: WorkorderReviewData = {
      id: `wrr-${Date.now()}`,
      orderId: orderId.value,
      reviewerUserId: 'user-004',
      decision: decision.value,
      comment: comment.value,
      evidenceNote: evidenceNote.value,
      createdAt: new Date().toISOString()
    }

    const reviews = getAllReviews().filter((item) => item.orderId !== orderId.value)
    saveReviews([reviewData, ...reviews])

    const nextStatus = decision.value === 'approved' ? 'closed' : 'doing'
    updateWorkorder(orderId.value, {
      status: nextStatus,
      reviewerUserId: reviewData.reviewerUserId,
      updatedAt: reviewData.createdAt,
    })
    appendEvent({
      id: `wot-${Date.now()}`,
      orderId: orderId.value,
      actorUserId: reviewData.reviewerUserId,
      action: decision.value === 'approved' ? 'closed' : 'reviewed',
      note: decision.value === 'approved'
        ? `人工复核通过：${comment.value}`
        : `人工复核驳回，返回现场核查：${comment.value}`,
      createdAt: reviewData.createdAt,
    })

    localStorage.removeItem(`workorder_review_draft_${orderId.value}`)

    const successMessage = decision.value === 'approved' 
      ? '复核已通过，工单将自动关闭' 
      : '复核已驳回，工单返回处理中状态'
    
    toast.success(successMessage)

    window.setTimeout(() => {
      window.location.href = `./workorder-detail.html?orderId=${encodeURIComponent(orderId.value)}`
    }, 600)
  } catch (error) {
    console.error('Submit error:', error)
    toast.error('提交失败，请重试')
    isSubmitting.value = false
  }
}

const handleBack = () => {
  window.location.href = `./workorder-detail.html?orderId=${orderId.value}`
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    loadData().finally(() => { isClient.value = true })
  })
})
</script>

<template>
  <div v-if="isClient && workorder && risk" class="h-full flex flex-col bg-background overflow-hidden">
    <PageHeader 
      :title="`复核工单：${workorder.title}`"
      :subtitle="`工单ID: ${workorder.id} | 风险等级: ${risk.level}`"
      :breadcrumb="breadcrumbItems"
    >
      <template #actions>
        <Button 
          variant="outline" 
          @click="handleBack"
          class="gap-2"
        >
          <SafeIcon name="ArrowLeft" :size="16" />
          返回
        </Button>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0 page-body">
      <div class="space-y-6 pb-8">
        <!-- 风险信息卡片 -->
        <Card class="surface-base border-border">
          <CardHeader class="pb-3">
            <div class="flex items-start justify-between">
              <div class="space-y-1">
                <CardTitle class="text-lg">关联风险信息</CardTitle>
                <CardDescription>来源风险详情与触发依据</CardDescription>
              </div>
              <StatusBadge :status="risk.level" size="sm" />
            </div>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1">
                <p class="text-xs text-muted-foreground uppercase tracking-wider">风险标题</p>
                <p class="text-sm font-medium text-foreground">{{ risk.title }}</p>
              </div>
              <div class="space-y-1">
                <p class="text-xs text-muted-foreground uppercase tracking-wider">风险分数</p>
                <p class="text-sm font-medium text-foreground">{{ risk.score }}/100</p>
              </div>
              <div class="space-y-1 col-span-2">
                <p class="text-xs text-muted-foreground uppercase tracking-wider">风险描述</p>
                <p class="text-sm text-card-foreground leading-relaxed">{{ risk.description }}</p>
              </div>
              <div class="space-y-1 col-span-2">
                <p class="text-xs text-muted-foreground uppercase tracking-wider">证据摘要</p>
                <p class="text-sm text-card-foreground leading-relaxed">{{ risk.evidenceSummary }}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <FieldLocationPanel
          :location="workorder.location || risk.location"
          title="复核空间位置"
          :label="risk.title"
        />

        <!-- 工单处理信息 -->
        <Card class="surface-base border-border">
          <CardHeader class="pb-3">
            <CardTitle class="text-lg">工单处理信息</CardTitle>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1">
                <p class="text-xs text-muted-foreground uppercase tracking-wider">工单ID</p>
                <p class="text-sm font-mono text-foreground">{{ workorder.id }}</p>
              </div>
              <div class="space-y-1">
                <p class="text-xs text-muted-foreground uppercase tracking-wider">当前状态</p>
                <StatusBadge :status="workorder.status" size="sm" />
              </div>
              <div class="space-y-1">
                <p class="text-xs text-muted-foreground uppercase tracking-wider">责任人</p>
                <p class="text-sm text-foreground">{{ workorder.assigneeUserName || '未分配' }}</p>
              </div>
              <div class="space-y-1">
                <p class="text-xs text-muted-foreground uppercase tracking-wider">处理摘要</p>
                <p class="text-sm text-card-foreground">{{ workorder.summary }}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Separator class="opacity-30" />

        <!-- 复核表单 -->
        <Card class="surface-raised border-border">
          <CardHeader class="pb-3">
            <CardTitle class="text-lg">复核决定</CardTitle>
            <CardDescription>请根据处理结果进行复核判定</CardDescription>
          </CardHeader>
          <CardContent class="space-y-6">
            <!-- 复核决定选择 -->
            <div class="space-y-3">
              <Label class="text-sm font-medium">复核结论</Label>
              <RadioGroup v-model="decision" class="space-y-2">
                <div class="flex items-center space-x-2 p-3 rounded-lg border border-border/50 hover:border-primary/30 hover:bg-primary/5 transition-all cursor-pointer group">
                  <RadioGroupItem value="approved" id="approved" class="group-hover:border-primary" />
                  <Label for="approved" class="flex-1 cursor-pointer">
                    <div class="space-y-0.5">
                      <p class="text-sm font-medium text-foreground">通过</p>
                      <p class="text-xs text-muted-foreground">处理结果符合预期，工单可关闭</p>
                    </div>
                  </Label>
                  <SafeIcon name="CheckCircle2" :size="20" class="text-[hsl(var(--success))] opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>

                <div class="flex items-center space-x-2 p-3 rounded-lg border border-border/50 hover:border-destructive/30 hover:bg-destructive/5 transition-all cursor-pointer group">
                  <RadioGroupItem value="rejected" id="rejected" class="group-hover:border-destructive" />
                  <Label for="rejected" class="flex-1 cursor-pointer">
                    <div class="space-y-0.5">
                      <p class="text-sm font-medium text-foreground">驳回</p>
                      <p class="text-xs text-muted-foreground">处理不符合要求，返回处理中状态</p>
                    </div>
                  </Label>
                  <SafeIcon name="XCircle" :size="20" class="text-destructive opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              </RadioGroup>
            </div>

            <!-- 证据说明 -->
            <div class="space-y-2">
              <Label for="evidence" class="text-sm font-medium">证据对比说明</Label>
              <p class="text-xs text-muted-foreground">描述处理前后的证据变化，支持处理结果的判定</p>
              <Textarea
                id="evidence"
                v-model="evidenceNote"
                placeholder="例如：处理前积水深度 1.2m，处理后降至 0.3m，符合预期标准..."
                class="min-h-24 bg-card/50 border-border focus:border-primary resize-none"
                @input="handleEvidenceNoteChange"
              />
              <p class="text-xs text-muted-foreground">{{ evidenceNote.length }}/500 字符</p>
            </div>

            <!-- 复核意见 -->
            <div class="space-y-2">
              <Label for="comment" class="text-sm font-medium">复核意见</Label>
              <p class="text-xs text-muted-foreground">填写复核过程中的发现、建议或后续跟进事项</p>
              <Textarea
                id="comment"
                v-model="comment"
                placeholder="例如：现场核验已完成，处置措施有效。建议后续加强该区域的定期巡检..."
                class="min-h-32 bg-card/50 border-border focus:border-primary resize-none"
                @input="handleCommentChange"
              />
              <p class="text-xs text-muted-foreground">{{ comment.length }}/1000 字符</p>
            </div>

            <!-- 复核人信息 -->
            <div class="p-3 rounded-lg bg-muted/20 border border-border/50 space-y-2">
              <p class="text-xs text-muted-foreground uppercase tracking-wider">复核人</p>
              <p class="text-sm font-medium text-foreground">{{ reviewerName }}</p>
              <p class="text-xs text-muted-foreground">{{ new Date().toLocaleString('zh-CN') }}</p>
            </div>
          </CardContent>
        </Card>

        <!-- 操作按钮 -->
        <div class="flex items-center justify-between gap-3 pt-4">
          <Button 
            variant="outline" 
            @click="handleBack"
            class="gap-2"
          >
            <SafeIcon name="X" :size="16" />
            取消
          </Button>

          <div class="flex items-center gap-3">
            <Button 
              variant="outline"
              :disabled="isSubmitting || !comment.trim() || !evidenceNote.trim()"
              @click="handleSubmit"
              class="gap-2"
            >
              <SafeIcon 
                v-if="!isSubmitting"
                name="Send" 
                :size="16" 
              />
              <SafeIcon 
                v-else
                name="Loader2" 
                :size="16" 
                class="animate-spin"
              />
              {{ isSubmitting ? '提交中...' : '提交复核' }}
            </Button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Loading state -->
  <div v-else class="h-full flex items-center justify-center bg-background">
    <div class="flex flex-col items-center gap-4">
      <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      <p class="text-sm text-muted-foreground">加载工单信息中...</p>
    </div>
  </div>
</template>

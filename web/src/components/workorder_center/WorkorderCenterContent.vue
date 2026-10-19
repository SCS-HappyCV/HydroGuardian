
<script setup lang="ts">
// 工单处理中心主组件：负责工单列表筛选、分页、详情抽屉和创建弹窗的交互。
import { ref, computed, watch, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import PageHeader from '@/components/common/PageHeader.vue'
import DataTable from '@/components/common/DataTable.vue'
import Pagination from '@/components/common/Pagination.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import WorkorderDetailPanel from './WorkorderDetailPanel.vue'
import WorkorderCreateDialog from './WorkorderCreateDialog.vue'
import * as WorkorderService from '@/data/WorkorderService'
import type { WorkorderVO } from '@/data/WorkorderService'
import { remoteAgentApi } from '@/api/remote-agent-api'
import { mapRemoteWorkorder } from '@/lib/remote-workorder-mapper'

const isClient = ref(true)
const allWorkorders = ref(WorkorderService.getAll())
const selectedWorkorder = ref<WorkorderVO | null>(null)
const showDetailPanel = ref(false)
const showCreateDialog = ref(false)
const prefilledRiskId = ref<string | null>(null)
const prefilledCaseId = ref<string | null>(null)

const statusFilter = ref<string>('all')
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

const closureStats = computed(() => {
  const items = allWorkorders.value
  const closed = items.filter((item) => item.status === 'closed').length
  const inProgress = items.filter((item) => item.status === 'doing').length
  const review = items.filter((item) => item.status === 'review').length
  return [
    { label: 'AI 已生成工单', value: items.length, suffix: '项', icon: 'Sparkles', tone: 'text-cyan-300', background: 'bg-cyan-300/[0.06] border-cyan-300/15' },
    { label: '现场处置中', value: inProgress, suffix: '项', icon: 'HardHat', tone: 'text-amber-300', background: 'bg-amber-300/[0.06] border-amber-300/15' },
    { label: '待复核确认', value: review, suffix: '项', icon: 'ClipboardCheck', tone: 'text-violet-300', background: 'bg-violet-300/[0.06] border-violet-300/15' },
    { label: '闭环完成率', value: items.length ? Math.round((closed / items.length) * 100) : 0, suffix: '%', icon: 'BadgeCheck', tone: 'text-emerald-300', background: 'bg-emerald-300/[0.06] border-emerald-300/15' },
  ]
})

// 根据状态和关键词过滤工单列表，保持列表、分页和统计使用同一份数据源。
const filteredWorkorders = computed(() => {
  let result = allWorkorders.value

  if (statusFilter.value !== 'all') {
    result = result.filter(wo => wo.status === statusFilter.value)
  }

  if (searchKeyword.value.trim()) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(wo =>
      wo.id.toLowerCase().includes(keyword) ||
      wo.title.toLowerCase().includes(keyword) ||
      wo.summary.toLowerCase().includes(keyword)
    )
  }

  return result
})

// 计算当前筛选条件下的总页数。
const totalPages = computed(() => Math.ceil(filteredWorkorders.value.length / pageSize.value))

// 按当前页码和分页大小截取表格实际展示的数据。
const paginatedWorkorders = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredWorkorders.value.slice(start, end)
})

const tableColumns = [
  { key: 'id', label: '工单ID', width: 'w-24', sortable: true },
  { key: 'title', label: '工单标题', width: 'min-w-0 max-w-xs', sortable: true },
  { key: 'status', label: '状态', width: 'w-20', sortable: true },
  { key: 'assigneeUserName', label: '责任人', width: 'w-24', sortable: false },
  { key: 'dueAt', label: '截止时间', width: 'w-32', sortable: true },
]

// 点击表格行后加载完整工单视图对象，并打开右侧详情面板。
const handleRowClick = (row: any) => {
  if (String(row.id).startsWith('wo_')) {
    window.location.href = `./workorder-detail.html?orderId=${encodeURIComponent(row.id)}`
    return
  }
  const vo = WorkorderService.getByIdVO(row.id)
  if (vo) {
    selectedWorkorder.value = vo
    showDetailPanel.value = true
  }
}

// 打开创建工单弹窗。
const handleCreateWorkorder = () => {
  showCreateDialog.value = true
}

// 工单创建成功后刷新列表，并回到第一页方便看到最新数据。
const handleWorkorderCreated = (newWorkorder: any) => {
  allWorkorders.value = WorkorderService.getAll()
  toast.success('工单创建成功')
  showCreateDialog.value = false
  currentPage.value = 1
  window.location.href = `./workorder-detail.html?orderId=${encodeURIComponent(newWorkorder.id)}`
}

// 切换状态筛选时重置页码，避免停留在无数据的高页码。
const handleStatusChange = (newStatus: string) => {
  statusFilter.value = newStatus
  currentPage.value = 1
}

// 切换当前页。
const handlePageChange = (page: number) => {
  currentPage.value = page
}

// 切换分页大小时回到第一页。
const handlePageSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
}

// 关闭详情面板并清理当前选择。
const handleCloseDetailPanel = () => {
  showDetailPanel.value = false
  selectedWorkorder.value = null
}

// 详情面板修改工单后刷新列表和当前选中工单。
const handleDetailPanelUpdate = () => {
  allWorkorders.value = WorkorderService.getAll()
  if (selectedWorkorder.value) {
    const updated = WorkorderService.getByIdVO(selectedWorkorder.value.id)
    if (updated) {
      selectedWorkorder.value = updated
    }
  }
}

// 页面挂载后读取 URL 查询参数，支持从风险页带 riskId 进入创建工单流程。
onMounted(() => {
  isClient.value = false
  requestAnimationFrame(async () => {
    try {
      const remote = (await remoteAgentApi.listWorkorders()).map(mapRemoteWorkorder)
      allWorkorders.value = [...remote, ...WorkorderService.getAll()]
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '处置工单同步失败')
      allWorkorders.value = WorkorderService.getAll()
    }
    isClient.value = true

    const searchParams = new URLSearchParams(window.location.search)
    const riskIdParam = searchParams.get('riskId')
    const caseIdParam = searchParams.get('caseId')
    const statusParam = searchParams.get('status')

    if (riskIdParam) {
      prefilledRiskId.value = riskIdParam
      prefilledCaseId.value = caseIdParam
      showCreateDialog.value = true
    }

    if (statusParam && ['todo', 'doing', 'review', 'closed'].includes(statusParam)) {
      statusFilter.value = statusParam
    }
  })
})

// 筛选结果变化后自动修正页码，防止当前页超过总页数。
watch(() => filteredWorkorders.value.length, () => {
  if (currentPage.value > totalPages.value && totalPages.value > 0) {
    currentPage.value = totalPages.value
  }
})
</script>

<template>
  <div v-if="isClient" class="flex flex-col h-full min-h-0 bg-background">
    <PageHeader
      title="处置闭环"
      subtitle="承接 AI 风险成果，追踪人工确认、现场处置与复核关闭"
      :breadcrumb="[
        { label: '首页', href: './dashboard.html' },
        { label: '工单中心' }
      ]"
    >
      <template #actions>
        <Button 
          class="gap-2 bg-primary hover:bg-primary-hover text-primary-foreground"
          @click="handleCreateWorkorder"
        >
          <SafeIcon name="Plus" :size="16" />
          创建工单
        </Button>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0 flex flex-col">
      <div class="grid grid-cols-2 gap-3 px-6 pt-4 xl:grid-cols-4">
        <article
          v-for="item in closureStats"
          :key="item.label"
          class="flex items-center justify-between rounded-xl border p-3"
          :class="item.background"
        >
          <div>
            <div class="text-[11px] text-muted-foreground">{{ item.label }}</div>
            <div class="mt-1 text-xl font-semibold text-foreground">{{ item.value }}<span class="ml-1 text-xs font-normal text-muted-foreground">{{ item.suffix }}</span></div>
          </div>
          <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-background/30" :class="item.tone">
            <SafeIcon :name="item.icon" :size="18" />
          </span>
        </article>
      </div>

      <div class="page-body pb-4 border-b border-border/50">
        <div class="flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-2">
            <label class="text-label whitespace-nowrap">工单状态</label>
            <Select :model-value="statusFilter" @update:model-value="handleStatusChange">
              <SelectTrigger class="w-[140px] h-9 bg-card/50">
                <SelectValue placeholder="选择状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="todo">待处理</SelectItem>
                <SelectItem value="doing">处理中</SelectItem>
                <SelectItem value="review">复核中</SelectItem>
                <SelectItem value="closed">已关闭</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="flex-1 min-w-[200px]">
            <div class="relative">
              <SafeIcon name="Search" :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                v-model="searchKeyword"
                placeholder="搜索工单ID、标题或备注..."
                class="pl-9 h-9 bg-card/50 border-border"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto min-h-0 page-body">
        <DataTable
          :columns="tableColumns"
          :data="paginatedWorkorders"
          row-key="id"
          :on-row-click="handleRowClick"
        >
          <template #cell-status="{ row }">
            <div :class="cn('inline-flex items-center px-2 py-1 rounded text-xs font-medium border', `status-badge-${row.status}`)">
              {{ { todo: '待处理', doing: '处理中', review: '复核中', closed: '已关闭' }[row.status] }}
            </div>
          </template>

          <template #cell-dueAt="{ row }">
            <span class="text-xs text-muted-foreground">
              {{ new Date(row.dueAt).toLocaleDateString('zh-CN') }}
            </span>
          </template>
        </DataTable>

        <Pagination
          :current-page="currentPage"
          :total-pages="totalPages"
          :page-size="pageSize"
          :total-items="filteredWorkorders.length"
          :on-page-change="handlePageChange"
          :on-page-size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <WorkorderDetailPanel
      v-if="selectedWorkorder && showDetailPanel"
      :workorder="selectedWorkorder"
      :open="showDetailPanel"
      @close="handleCloseDetailPanel"
      @update="handleDetailPanelUpdate"
    />

    <WorkorderCreateDialog
      :open="showCreateDialog"
      :prefilled-risk-id="prefilledRiskId"
      :prefilled-case-id="prefilledCaseId"
      @close="() => showCreateDialog = false"
      @created="handleWorkorderCreated"
    />
  </div>
</template>

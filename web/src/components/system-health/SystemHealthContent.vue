
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as SystemHealthService from '@/data/SystemHealthService'
import * as SystemLogService from '@/data/SystemLogService'
import type { SystemHealthData } from '@/data/SystemHealthData'
import type { SystemLogData } from '@/data/SystemLogData'
import PageHeader from '@/components/common/PageHeader.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ServiceHealthCard from '@/components/system-health/ServiceHealthCard.vue'
import SystemLogList from '@/components/system-health/SystemLogList.vue'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'

const healthData = ref<SystemHealthData[]>(SystemHealthService.getAll())
const logData = ref<SystemLogData[]>(SystemLogService.query({}))
const isClient = ref(true)

const selectedServiceKey = ref<string | null>(null)
const categoryFilter = ref<string>('all')
const logLevelFilter = ref<string>('all')
const activeTab = ref<'health' | 'logs'>('health')

const filteredHealthData = computed(() => {
  let result = healthData.value
  
  if (categoryFilter.value !== 'all') {
    result = result.filter(item => item.category === categoryFilter.value)
  }
  
  if (selectedServiceKey.value) {
    result = result.filter(item => item.serviceKey === selectedServiceKey.value)
  }
  
  return result
})

const filteredLogData = computed(() => {
  let result = logData.value
  
  if (logLevelFilter.value !== 'all') {
    result = result.filter(item => item.level === logLevelFilter.value)
  }
  
  if (selectedServiceKey.value) {
    result = result.filter(item => item.serviceHealthId === selectedServiceKey.value || item.serviceHealthId === healthData.value.find(h => h.serviceKey === selectedServiceKey.value)?.id)
  }
  
  return result
})

const healthFilters = [
  {
    key: 'category',
    label: '服务类型',
    options: [
      { value: 'all', label: '全部' },
      { value: 'backend', label: '后端服务' },
      { value: 'model', label: '模型服务' },
      { value: 'database', label: '数据库' }
    ]
  }
]

const logFilters = [
  {
    key: 'level',
    label: '日志级别',
    options: [
      { value: 'all', label: '全部' },
      { value: 'info', label: '信息' },
      { value: 'warn', label: '警告' },
      { value: 'error', label: '错误' }
    ]
  }
]

const handleHealthFilterChange = (filters: Record<string, string>) => {
  categoryFilter.value = filters.category || 'all'
}

const handleLogFilterChange = (filters: Record<string, string>) => {
  logLevelFilter.value = filters.level || 'all'
}

const handleSelectService = (serviceKey: string) => {
  selectedServiceKey.value = selectedServiceKey.value === serviceKey ? null : serviceKey
  activeTab.value = 'logs'
}

const handleRetry = (serviceKey: string, event: Event) => {
  event.stopPropagation()
  const service = healthData.value.find(s => s.serviceKey === serviceKey)
  if (service) {
    service.status = 'degraded'
    service.errorCount = Math.max(0, service.errorCount - 1)
    toast.success(`已提交 ${service.serviceName} 重试请求`)
  }
}

const breadcrumb = [
  { label: '系统设置', href: './settings.html' },
  { label: '系统健康详情' }
]

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true
    
    const params = new URLSearchParams(window.location.search)
    const serviceKey = params.get('serviceKey')
    if (serviceKey) {
      selectedServiceKey.value = serviceKey
      activeTab.value = 'logs'
    }
  })
})
</script>

<template>
  <div v-if="isClient" class="flex flex-col h-full min-h-0 bg-background">
    <PageHeader 
      title="系统健康详情"
      subtitle="实时监控后端服务、AI模型及数据库的运行状态"
      :breadcrumb="breadcrumb"
    />

    <div class="flex-1 overflow-y-auto min-h-0 page-body">
      <Tabs v-model="activeTab" class="w-full space-y-4">
        <TabsList class="grid w-full max-w-md grid-cols-2 bg-card/40 border border-border">
          <TabsTrigger value="health" class="data-[state=active]:bg-primary/20">
            <SafeIcon name="Activity" :size="16" class="mr-2" />
            服务状态
          </TabsTrigger>
          <TabsTrigger value="logs" class="data-[state=active]:bg-primary/20">
            <SafeIcon name="FileText" :size="16" class="mr-2" />
            错误日志
          </TabsTrigger>
        </TabsList>

        <TabsContent value="health" class="space-y-4 mt-4">
          <FilterBar 
            :filters="healthFilters"
            :model-value="{ category: categoryFilter }"
            @update:model-value="handleHealthFilterChange"
          />

          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <ServiceHealthCard
              v-for="service in filteredHealthData"
              :key="service.id"
              :service="service"
              :is-selected="selectedServiceKey === service.serviceKey"
              @select="handleSelectService"
              @retry="handleRetry"
            />
          </div>

          <div v-if="filteredHealthData.length === 0" class="text-center py-12 text-muted-foreground">
            <SafeIcon name="Inbox" :size="32" class="mx-auto mb-2 opacity-20" />
            <p>暂无匹配的服务数据</p>
          </div>
        </TabsContent>

        <TabsContent value="logs" class="space-y-4 mt-4">
          <FilterBar 
            :filters="logFilters"
            :model-value="{ level: logLevelFilter }"
            @update:model-value="handleLogFilterChange"
          />

          <SystemLogList 
            :logs="filteredLogData"
            :selected-service-key="selectedServiceKey"
          />
        </TabsContent>
      </Tabs>
    </div>
  </div>
</template>

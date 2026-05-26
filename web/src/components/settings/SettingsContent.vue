
<script setup lang="ts">
import { ref, computed } from 'vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import PageHeader from '@/components/common/PageHeader.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'
import * as SettingService from '@/data/SettingService'
import BasicSettingsForm from './BasicSettingsForm.vue'
import DataSourceSettingsForm from './DataSourceSettingsForm.vue'
import ApiSettingsForm from './ApiSettingsForm.vue'
import SecuritySettingsForm from './SecuritySettingsForm.vue'

const isClient = ref(true)
const activeTab = ref('basic')
const allSettings = ref(SettingService.getAll())
const hasUnsavedChanges = ref(false)

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true
  })

  const params = new URLSearchParams(window.location.search)
  const tabParam = params.get('activeTab')
  if (tabParam && ['basic', 'data', 'api', 'security'].includes(tabParam)) {
    activeTab.value = tabParam
  }
})

const handleTabChange = (tab: string) => {
  if (hasUnsavedChanges.value) {
    toast.warning('您有未保存的更改，请先保存或取消')
    return
  }
  activeTab.value = tab
  const url = new URL(window.location)
  url.searchParams.set('activeTab', tab)
  window.history.replaceState({}, '', url)
}

const handleSettingsUpdate = (updatedSettings: any[]) => {
  allSettings.value = updatedSettings
  hasUnsavedChanges.value = true
}

const handleSave = () => {
  SettingService.savePersisted(allSettings.value)
  hasUnsavedChanges.value = false
  toast.success('设置已保存')
}

const handleReset = () => {
  allSettings.value = SettingService.getAll()
  hasUnsavedChanges.value = false
  toast.info('已取消修改')
}

const handleNavigateToUsers = () => {
  window.location.href = './user-perm-management.html'
}

const handleNavigateToHealth = () => {
  window.location.href = './system-health.html'
}

const handleNavigateToDashboard = () => {
  window.location.href = './dashboard.html'
}
</script>

<template>
  <div v-if="isClient" class="h-full flex flex-col bg-background overflow-hidden">
    <PageHeader 
      title="系统设置" 
      subtitle="管理系统运行参数、数据源连接及权限配置"
      :breadcrumb="[
        { label: '首页', href: './dashboard.html' },
        { label: '系统设置' }
      ]"
    >
      <template #actions>
        <Button 
          variant="outline" 
          size="sm"
          @click="handleNavigateToDashboard"
          class="gap-2"
        >
          <SafeIcon name="ArrowLeft" :size="16" />
          返回
        </Button>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0 page-body">
      <div class="max-w-4xl mx-auto space-y-6">
        <Tabs :value="activeTab" @update:value="handleTabChange" class="w-full">
          <TabsList class="grid w-full grid-cols-4 bg-card/40 border border-border rounded-lg p-1 mb-6">
            <TabsTrigger value="basic" class="gap-2 data-[state=active]:bg-primary/20 data-[state=active]:text-primary">
              <SafeIcon name="Settings" :size="16" />
              <span class="hidden sm:inline">基础设置</span>
            </TabsTrigger>
            <TabsTrigger value="data" class="gap-2 data-[state=active]:bg-primary/20 data-[state=active]:text-primary">
              <SafeIcon name="Database" :size="16" />
              <span class="hidden sm:inline">数据源</span>
            </TabsTrigger>
            <TabsTrigger value="api" class="gap-2 data-[state=active]:bg-primary/20 data-[state=active]:text-primary">
              <SafeIcon name="Zap" :size="16" />
              <span class="hidden sm:inline">API 配置</span>
            </TabsTrigger>
            <TabsTrigger value="security" class="gap-2 data-[state=active]:bg-primary/20 data-[state=active]:text-primary">
              <SafeIcon name="Lock" :size="16" />
              <span class="hidden sm:inline">安全</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="basic" class="space-y-4">
            <BasicSettingsForm 
              :settings="allSettings" 
              @update="handleSettingsUpdate"
            />
          </TabsContent>

          <TabsContent value="data" class="space-y-4">
            <DataSourceSettingsForm 
              :settings="allSettings" 
              @update="handleSettingsUpdate"
            />
          </TabsContent>

          <TabsContent value="api" class="space-y-4">
            <ApiSettingsForm 
              :settings="allSettings" 
              @update="handleSettingsUpdate"
            />
          </TabsContent>

          <TabsContent value="security" class="space-y-4">
            <SecuritySettingsForm 
              :settings="allSettings" 
              @update="handleSettingsUpdate"
            />
          </TabsContent>
        </Tabs>

        <div class="surface-base card-padding flex items-center justify-between gap-4 sticky bottom-0">
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <div v-if="hasUnsavedChanges" class="flex items-center gap-2 text-accent">
              <SafeIcon name="AlertCircle" :size="16" />
              <span>您有未保存的更改</span>
            </div>
            <div v-else class="flex items-center gap-2 text-[hsl(var(--success))]">
              <SafeIcon name="CheckCircle2" :size="16" />
              <span>所有更改已保存</span>
            </div>
          </div>

          <div class="flex items-center gap-3">
            <Button 
              variant="outline" 
              @click="handleReset"
              :disabled="!hasUnsavedChanges"
              class="gap-2"
            >
              <SafeIcon name="RotateCcw" :size="16" />
              取消
            </Button>
            <Button 
              @click="handleSave"
              :disabled="!hasUnsavedChanges"
              class="gap-2 bg-primary hover:bg-primary-hover text-primary-foreground"
            >
              <SafeIcon name="Save" :size="16" />
              保存设置
            </Button>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8">
          <div class="surface-base card-padding space-y-3 cursor-pointer hover:surface-raised transition-all" @click="handleNavigateToUsers">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
                <SafeIcon name="Users" :size="20" class="text-primary" />
              </div>
              <div>
                <h4 class="text-item-title">成员与角色管理</h4>
                <p class="text-caption">配置用户权限和角色分配</p>
              </div>
            </div>
            <div class="flex items-center text-primary text-xs font-medium">
              <span>进入管理</span>
              <SafeIcon name="ChevronRight" :size="14" class="ml-1" />
            </div>
          </div>

          <div class="surface-base card-padding space-y-3 cursor-pointer hover:surface-raised transition-all" @click="handleNavigateToHealth">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center">
                <SafeIcon name="Activity" :size="20" class="text-accent" />
              </div>
              <div>
                <h4 class="text-item-title">系统健康状态</h4>
                <p class="text-caption">查看服务运行状态和性能指标</p>
              </div>
            </div>
            <div class="flex items-center text-accent text-xs font-medium">
              <span>查看详情</span>
              <SafeIcon name="ChevronRight" :size="14" class="ml-1" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>


<script setup lang="ts">
import {
  Sidebar,
  SidebarContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarSeparator,
  SidebarFooter
} from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { usePresentationMode } from '@/lib/presentation-mode'

const props = defineProps<{
  currentPath: string
}>()

const pendingWorkorders = ref(12)
const { isCompetitionMode, initializePresentationMode } = usePresentationMode()

const competitionNavigationItems = [
  {
    title: '智巡总览',
    icon: 'LayoutDashboard',
    href: './dashboard.html',
    id: 'dashboard'
  },
  {
    title: '发起巡查',
    icon: 'MessageSquareText',
    href: './task-studio.html',
    id: 'task-studio'
  },
  {
    title: '智能执行',
    icon: 'Network',
    href: './task-execution-monitor.html',
    id: 'task-execution-monitor'
  },
  {
    title: '历史任务',
    icon: 'ListVideo',
    href: './task-history.html',
    id: 'task-history'
  },
  {
    title: '风险研判',
    icon: 'ScanSearch',
    href: './risk-workspace.html',
    id: 'risk-workspace'
  },
  {
    title: '处置闭环',
    icon: 'ClipboardCheck',
    href: './workorder-center.html',
    id: 'workorder-center',
    badge: true
  }
]

const operationsNavigationItems = [
  { title: '全局总览', icon: 'LayoutDashboard', href: './dashboard.html', id: 'dashboard' },
  { title: '任务工作坊', icon: 'Hammer', href: './task-studio.html', id: 'task-studio' },
  { title: '执行监控', icon: 'Activity', href: './task-execution-monitor.html', id: 'task-execution-monitor' },
  { title: '历史任务', icon: 'ListVideo', href: './task-history.html', id: 'task-history' },
  { title: '风险分析区', icon: 'Map', href: './risk-workspace.html', id: 'risk-workspace' },
  { title: '工单中心', icon: 'ClipboardList', href: './workorder-center.html', id: 'workorder-center', badge: true },
]

const navigationItems = computed(() => isCompetitionMode.value ? competitionNavigationItems : operationsNavigationItems)

const manageItems = [
  {
    title: '知识库管理',
    icon: 'BookOpen',
    href: './knowledge.html',
    id: 'knowledge'
  },
  {
    title: '系统设置',
    icon: 'Settings',
    href: './settings.html',
    id: 'settings'
  }
]

const isActive = (href: string) => {
  const normalizedHref = href.replace(/^\.\//, '').replace(/\.html$/, '')
  const normalizedPath = (props.currentPath || '').replace(/^\//, '').replace(/\.html$/, '')
  return normalizedPath === normalizedHref || (normalizedHref !== 'dashboard' && normalizedPath.startsWith(normalizedHref))
}

onMounted(() => {
  initializePresentationMode()
})

const handleRefresh = () => {
  window.location.reload()
}
</script>

<template>
  <Sidebar variant="inset" class="h-full border-r border-border/50">
    <SidebarContent>
      <SidebarGroup class="mt-4">
        <SidebarGroupLabel class="text-[10px] uppercase tracking-wider font-bold text-muted-foreground/60 mb-2 px-4">
          AI 智巡链路
        </SidebarGroupLabel>
        <SidebarMenu>
          <SidebarMenuItem v-for="item in navigationItems" :key="item.id">
            <SidebarMenuButton 
              as-child 
              :active="isActive(item.href)"
              class="w-full relative px-4"
              :class="cn('hover:bg-muted/50 transition-all duration-200', isActive(item.href) && 'nav-item-active')"
            >
              <a :href="item.href" class="flex items-center gap-3 py-2">
                <SafeIcon 
                  :name="item.icon" 
                  :size="18" 
                  :class="isActive(item.href) ? 'text-primary' : 'text-muted-foreground'"
                />
                <span class="text-sm">{{ item.title }}</span>
                <Badge 
                  v-if="item.badge && pendingWorkorders > 0" 
                  variant="secondary" 
                  class="ml-auto bg-primary/20 text-primary border-primary/20 text-[10px] h-5 min-w-5 flex items-center justify-center"
                >
                  {{ pendingWorkorders }}
                </Badge>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>

      <SidebarSeparator v-if="!isCompetitionMode" class="mx-4 my-4 opacity-50" />

      <SidebarGroup v-if="!isCompetitionMode">
        <SidebarGroupLabel class="text-[10px] uppercase tracking-wider font-bold text-muted-foreground/60 mb-2 px-4">
          系统管理
        </SidebarGroupLabel>
        <SidebarMenu>
          <SidebarMenuItem v-for="item in manageItems" :key="item.id">
            <SidebarMenuButton 
              as-child 
              :active="isActive(item.href)"
              class="w-full px-4"
              :class="cn('hover:bg-muted/50 transition-all duration-200', isActive(item.href) && 'nav-item-active')"
            >
              <a :href="item.href" class="flex items-center gap-3 py-2">
                <SafeIcon 
                  :name="item.icon" 
                  :size="18" 
                  :class="isActive(item.href) ? 'text-primary' : 'text-muted-foreground'"
                />
                <span class="text-sm">{{ item.title }}</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    </SidebarContent>

    <SidebarFooter class="p-4">
      <div class="surface-base p-3 flex items-center gap-3">
        <div class="w-2 h-2 rounded-full bg-[hsl(var(--success))] shadow-[0_0_8px_hsl(var(--success) / 0.5)]" />
        <div class="flex-1">
          <p class="text-[10px] text-muted-foreground">{{ isCompetitionMode ? '业务协同状态' : '数据同步状态' }}</p>
          <p class="text-[11px] font-medium">{{ isCompetitionMode ? '典型案例已就绪' : '实时/已连接' }}</p>
        </div>
        <Button variant="ghost" size="icon" class="h-6 w-6" title="刷新当前页面" @click="handleRefresh">
          <SafeIcon name="RefreshCw" :size="12" />
        </Button>
      </div>
    </SidebarFooter>
  </Sidebar>
</template>

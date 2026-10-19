<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'
import { useAuthState } from '@/lib/auth'
import { usePresentationMode } from '@/lib/presentation-mode'

const props = defineProps<{
  currentPath: string
}>()

const taskQueueCount = ref(3)
const systemStatus = ref<'normal' | 'warning' | 'error'>('normal')
const { authUser, loadAuthState } = useAuthState()
const { isCompetitionMode, initializePresentationMode } = usePresentationMode()

const handleSearch = () => {
  toast.info('全局搜索功能正在开发中')
}

onMounted(() => {
  loadAuthState()
  initializePresentationMode()
})

const handleOpenTaskQueue = () => {
  window.location.href = './task-execution-monitor.html'
}

const handleOpenNotifications = () => {
  toast.info('3 条巡查动态已汇总，可在智能执行与处置闭环中查看')
}

const handleOpenSettings = () => {
  window.location.href = './settings.html'
}

const handleOpenHistory = () => {
  window.location.href = './history.html'
}
</script>

<template>
  <header class="sticky top-0 z-50 w-full h-[60px] border-b border-border bg-background/80 backdrop-blur-md px-4 flex items-center justify-between">
    <div class="flex items-center gap-6">
      <a href="." class="flex items-center gap-2 group">
        <div class="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground shadow-lg shadow-primary/20 group-hover:scale-105 transition-transform">
          <SafeIcon name="Waves" :size="20" />
        </div>
        <span class="text-xl font-bold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text">
          HydroGuardian 水利智巡
        </span>
      </a>

      <div class="hidden md:flex items-center gap-4 px-4 border-l border-border h-6">
        <div class="flex items-center gap-1.5">
          <div :class="cn('w-2 h-2 rounded-full animate-pulse', systemStatus === 'normal' ? 'bg-[hsl(var(--success))]' : 'bg-destructive')" />
          <span class="text-xs text-muted-foreground">{{ isCompetitionMode ? '典型案例已就绪' : '系统运行正常' }}</span>
        </div>
      </div>
    </div>

    <div v-if="!isCompetitionMode" class="flex-1 max-w-md mx-8 hidden lg:block">
      <div class="relative group">
        <SafeIcon name="Search" :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors" />
        <Input
          placeholder="搜索任务、工单或风险点..."
          class="pl-9 bg-muted/30 border-none focus-visible:ring-1 focus-visible:ring-primary h-9"
          @keyup.enter="handleSearch"
        />
      </div>
    </div>

    <div class="flex items-center gap-3">
      <div v-if="!isCompetitionMode" class="flex items-center gap-1">
        <Button variant="ghost" size="icon" class="relative" title="任务队列" @click="handleOpenTaskQueue">
          <SafeIcon name="ListTodo" :size="20" />
          <Badge v-if="taskQueueCount > 0" class="absolute -top-1 -right-1 h-5 w-5 flex items-center justify-center p-0 text-[10px] bg-primary text-primary-foreground border-2 border-background">
            {{ taskQueueCount }}
          </Badge>
        </Button>

        <Button variant="ghost" size="icon" class="relative" title="通知消息" @click="handleOpenNotifications">
          <SafeIcon name="Bell" :size="20" />
          <div class="absolute top-2 right-2.5 h-2 w-2 bg-destructive rounded-full border border-background" />
        </Button>

        <Button variant="ghost" size="icon" title="系统帮助" @click="toast('帮助文档请查看内部知识库')">
          <SafeIcon name="HelpCircle" :size="20" />
        </Button>
      </div>

      <div v-if="!isCompetitionMode" class="w-px h-6 bg-border mx-1" />

      <DropdownMenu v-if="!isCompetitionMode && authUser">
        <DropdownMenuTrigger as-child>
          <Button variant="ghost" class="gap-2 px-2 hover:bg-muted/50 transition-colors">
            <Avatar class="h-8 w-8 border border-border">
              <AvatarImage v-if="!isCompetitionMode && authUser.avatarUrl" :src="authUser.avatarUrl" alt="User" />
              <AvatarFallback>{{ authUser.name.slice(0, 2) }}</AvatarFallback>
            </Avatar>
            <div class="flex flex-col items-start text-left hidden sm:flex">
              <span class="text-sm font-medium leading-none">{{ authUser.name }}</span>
              <span class="text-[10px] text-muted-foreground mt-0.5">{{ authUser.department || authUser.role || '-' }}</span>
            </div>
            <SafeIcon name="ChevronDown" :size="14" class="text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-56">
          <DropdownMenuLabel>我的账户</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="cursor-pointer" @click="handleOpenSettings">
            <SafeIcon name="User" :size="14" class="mr-2" /> 个人设置
          </DropdownMenuItem>
          <DropdownMenuItem class="cursor-pointer" @click="handleOpenHistory">
            <SafeIcon name="History" :size="14" class="mr-2" /> 我的足迹
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <div v-else class="hidden items-center gap-2 rounded-full border border-accent/20 bg-accent/[0.08] px-3 py-1.5 text-xs text-accent sm:flex">
        <SafeIcon name="ShieldCheck" :size="14" />
        AI 全链路就绪
      </div>
    </div>
  </header>
</template>

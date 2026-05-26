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
import { clearAuthSession, useAuthState } from '@/lib/auth'

const props = defineProps<{
  currentPath: string
}>()

const taskQueueCount = ref(3)
const systemStatus = ref<'normal' | 'warning' | 'error'>('normal')
const defaultAvatar = 'https://spark-builder.s3.cn-north-1.amazonaws.com.cn/image/2026/5/25/77fefb85-a38b-48f8-8e7d-e7a6df12426d.png'
const { authUser, isLoggedIn, loadAuthState } = useAuthState()

const handleSearch = () => {
  toast.info('全局搜索功能正在开发中')
}

onMounted(() => {
  loadAuthState()
})

const handleGoToLogin = () => {
  if (typeof window === 'undefined') return

  const redirectUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`
  window.location.href = `./page-3205032.html?redirectUrl=${encodeURIComponent(redirectUrl)}`
}

const handleSignOut = () => {
  clearAuthSession()
  toast.success('已安全退出登录')
}
</script>

<template>
  <header class="sticky top-0 z-50 w-full h-[60px] border-b border-border bg-background/80 backdrop-blur-md px-4 flex items-center justify-between">
    <div class="flex items-center gap-6">
      <a href="." class="flex items-center gap-2 group">
        <div class="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground shadow-lg shadow-primary/20 group-hover:scale-105 transition-transform">
          <SafeIcon name="ShieldAlert" :size="20" />
        </div>
        <span class="text-xl font-bold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text">
          风险哨兵系统
        </span>
      </a>

      <div class="hidden md:flex items-center gap-4 px-4 border-l border-border h-6">
        <div class="flex items-center gap-1.5">
          <div :class="cn('w-2 h-2 rounded-full animate-pulse', systemStatus === 'normal' ? 'bg-[hsl(var(--success))]' : 'bg-destructive')" />
          <span class="text-xs text-muted-foreground">系统运行正常</span>
        </div>
      </div>
    </div>

    <div class="flex-1 max-w-md mx-8 hidden lg:block">
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
      <div class="flex items-center gap-1">
        <Button variant="ghost" size="icon" class="relative" title="任务队列">
          <SafeIcon name="ListTodo" :size="20" />
          <Badge v-if="taskQueueCount > 0" class="absolute -top-1 -right-1 h-5 w-5 flex items-center justify-center p-0 text-[10px] bg-primary text-primary-foreground border-2 border-background">
            {{ taskQueueCount }}
          </Badge>
        </Button>

        <Button variant="ghost" size="icon" class="relative" title="通知消息">
          <SafeIcon name="Bell" :size="20" />
          <div class="absolute top-2 right-2.5 h-2 w-2 bg-destructive rounded-full border border-background" />
        </Button>

        <Button variant="ghost" size="icon" title="系统帮助" @click="toast('帮助文档请查看内部知识库')">
          <SafeIcon name="HelpCircle" :size="20" />
        </Button>
      </div>

      <div class="w-px h-6 bg-border mx-1" />

      <DropdownMenu v-if="isLoggedIn && authUser">
        <DropdownMenuTrigger as-child>
          <Button variant="ghost" class="gap-2 px-2 hover:bg-muted/50 transition-colors">
            <Avatar class="h-8 w-8 border border-border">
              <AvatarImage :src="authUser.avatarUrl || defaultAvatar" alt="User" />
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
          <DropdownMenuItem class="cursor-pointer">
            <SafeIcon name="User" :size="14" class="mr-2" /> 个人设置
          </DropdownMenuItem>
          <DropdownMenuItem class="cursor-pointer">
            <SafeIcon name="History" :size="14" class="mr-2" /> 我的足迹
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="text-destructive cursor-pointer" @click="handleSignOut">
            <SafeIcon name="LogOut" :size="14" class="mr-2" /> 退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Button v-else variant="default" class="gap-2 px-3" @click="handleGoToLogin">
        <SafeIcon name="LogIn" :size="14" />
        登录
      </Button>
    </div>
  </header>
</template>

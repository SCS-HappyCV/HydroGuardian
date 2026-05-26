
<script setup lang="ts">
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'

interface User {
  id: string
  name: string
  email: string
  roleId: string
  projectId: string
  datasetId: string
  status: 'active' | 'disabled'
  avatarUrl: string
  createdAt: string
  updatedAt: string
}

const props = defineProps<{
  users: User[]
}>()

const emit = defineEmits<{
  (e: 'edit', user: User): void
  (e: 'delete', userId: string): void
}>()

const getRoleLabel = (roleId: string) => {
  const roleMap: Record<string, string> = {
    'role-001': '平台管理员',
    'role-002': '巡检负责人',
    'role-003': '风险分析师',
    'role-004': '复核经理',
  }
  return roleMap[roleId] || '未知角色'
}

const getStatusColor = (status: string) => {
  return status === 'active' ? 'bg-[hsl(var(--success))]/20 text-[hsl(var(--success))]' : 'bg-destructive/20 text-destructive'
}
</script>

<template>
  <div class="surface-base rounded-lg overflow-hidden">
    <div class="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent border-b border-border/50">
            <TableHead class="w-12 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              用户
            </TableHead>
            <TableHead class="w-48 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              邮箱
            </TableHead>
            <TableHead class="w-32 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              角色
            </TableHead>
            <TableHead class="w-32 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              项目
            </TableHead>
            <TableHead class="w-32 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              数据集
            </TableHead>
            <TableHead class="w-20 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              状态
            </TableHead>
            <TableHead class="w-24 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              操作
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow 
            v-for="user in users"
            :key="user.id"
            class="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors"
          >
            <TableCell class="px-4 py-3">
              <Avatar class="h-8 w-8 border border-border">
                <AvatarImage :src="user.avatarUrl" :alt="user.name" />
                <AvatarFallback class="text-[10px]">{{ user.name.slice(0, 2) }}</AvatarFallback>
              </Avatar>
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-card-foreground truncate">
              <div class="space-y-0.5">
                <p class="font-medium">{{ user.name }}</p>
                <p class="text-[10px] text-muted-foreground">{{ user.id }}</p>
              </div>
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-card-foreground">
              {{ user.email }}
            </TableCell>
            <TableCell class="px-4 py-3 text-sm">
              <Badge variant="outline" class="bg-primary/10 text-primary border-primary/20">
                {{ getRoleLabel(user.roleId) }}
              </Badge>
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-card-foreground">
              <span class="text-[10px] text-muted-foreground">{{ user.projectId }}</span>
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-card-foreground">
              <span class="text-[10px] text-muted-foreground">{{ user.datasetId }}</span>
            </TableCell>
            <TableCell class="px-4 py-3">
              <Badge 
                variant="outline"
                :class="cn('text-[10px] border-0', getStatusColor(user.status))"
              >
                {{ user.status === 'active' ? '活跃' : '禁用' }}
              </Badge>
            </TableCell>
            <TableCell class="px-4 py-3">
              <div class="flex items-center gap-1">
                <Button 
                  variant="ghost" 
                  size="icon" 
                  class="h-7 w-7 text-muted-foreground hover:text-primary"
                  @click="emit('edit', user)"
                >
                  <SafeIcon name="Edit2" :size="14" />
                </Button>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  class="h-7 w-7 text-muted-foreground hover:text-destructive"
                  @click="emit('delete', user.id)"
                >
                  <SafeIcon name="Trash2" :size="14" />
                </Button>
              </div>
            </TableCell>
          </TableRow>

          <TableRow v-if="users.length === 0">
            <TableCell :colspan="7" class="h-32 text-center">
              <div class="flex flex-col items-center justify-center text-muted-foreground">
                <SafeIcon name="Users" :size="32" class="mb-2 opacity-20" />
                <span class="text-sm">暂无用户数据</span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>

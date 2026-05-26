
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
import { Checkbox } from '@/components/ui/checkbox'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { cn } from '@/lib/utils'

interface Role {
  id: string
  name: string
  code: string
  description: string
  permissionCount: number
  isSystem: boolean
  createdAt: string
  updatedAt: string
}

const props = defineProps<{
  roles: Role[]
}>()

const emit = defineEmits<{
  (e: 'edit', role: Role): void
  (e: 'delete', roleId: string): void
  (e: 'permission-change', roleId: string, updatedRole: Role): void
}>()

const permissions = [
  { id: 'view_dashboard', label: '查看总览' },
  { id: 'create_task', label: '创建任务' },
  { id: 'view_risk', label: '查看风险' },
  { id: 'manage_workorder', label: '管理工单' },
  { id: 'review_workorder', label: '复核工单' },
  { id: 'manage_knowledge', label: '管理知识库' },
  { id: 'manage_user', label: '管理用户' },
  { id: 'manage_system', label: '管理系统' },
]

const rolePermissions = ref<Record<string, Set<string>>>({})

onMounted(() => {
  props.roles.forEach(role => {
    rolePermissions.value[role.id] = new Set(
      Array.from({ length: role.permissionCount }, (_, i) => permissions[i]?.id).filter(Boolean)
    )
  })
})

const togglePermission = (roleId: string, permissionId: string) => {
  const perms = rolePermissions.value[roleId]
  if (perms.has(permissionId)) {
    perms.delete(permissionId)
  } else {
    perms.add(permissionId)
  }

  const role = props.roles.find(r => r.id === roleId)
  if (role) {
    const updatedRole = {
      ...role,
      permissionCount: perms.size,
    }
    emit('permission-change', roleId, updatedRole)
  }
}

const hasPermission = (roleId: string, permissionId: string) => {
  return rolePermissions.value[roleId]?.has(permissionId) ?? false
}
</script>

<template>
  <div class="surface-base rounded-lg overflow-hidden">
    <div class="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent border-b border-border/50">
            <TableHead class="w-40 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              角色
            </TableHead>
            <template v-for="perm in permissions" :key="perm.id">
              <TableHead class="w-20 whitespace-nowrap h-12 px-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider text-center">
                {{ perm.label }}
              </TableHead>
            </template>
            <TableHead class="w-24 whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              操作
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow 
            v-for="role in roles"
            :key="role.id"
            class="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors"
          >
            <TableCell class="px-4 py-3">
              <div class="space-y-1">
                <div class="flex items-center gap-2">
                  <p class="font-medium text-sm">{{ role.name }}</p>
                  <Badge 
                    v-if="role.isSystem"
                    variant="secondary"
                    class="text-[10px] bg-accent/20 text-accent border-accent/20"
                  >
                    系统
                  </Badge>
                </div>
                <p class="text-[10px] text-muted-foreground">{{ role.code }}</p>
              </div>
            </TableCell>
            <template v-for="perm in permissions" :key="perm.id">
              <TableCell class="px-2 py-3 text-center">
                <Checkbox 
                  :checked="hasPermission(role.id, perm.id)"
                  :disabled="role.isSystem"
                  @update:checked="togglePermission(role.id, perm.id)"
                  class="mx-auto"
                />
              </TableCell>
            </template>
            <TableCell class="px-4 py-3">
              <div class="flex items-center gap-1">
                <Button 
                  variant="ghost" 
                  size="icon" 
                  class="h-7 w-7 text-muted-foreground hover:text-primary"
                  :disabled="role.isSystem"
                  @click="emit('edit', role)"
                >
                  <SafeIcon name="Edit2" :size="14" />
                </Button>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  class="h-7 w-7 text-muted-foreground hover:text-destructive"
                  :disabled="role.isSystem"
                  @click="emit('delete', role.id)"
                >
                  <SafeIcon name="Trash2" :size="14" />
                </Button>
              </div>
            </TableCell>
          </TableRow>

          <TableRow v-if="roles.length === 0">
            <TableCell :colspan="permissions.length + 2" class="h-32 text-center">
              <div class="flex flex-col items-center justify-center text-muted-foreground">
                <SafeIcon name="Shield" :size="32" class="mb-2 opacity-20" />
                <span class="text-sm">暂无角色数据</span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>

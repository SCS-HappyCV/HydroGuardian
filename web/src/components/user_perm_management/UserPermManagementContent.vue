
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import SafeIcon from '@/components/common/SafeIcon.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import SearchBar from '@/components/common/SearchBar.vue'
import UserPermissionTable from './UserPermissionTable.vue'
import RolePermissionMatrix from './RolePermissionMatrix.vue'
import UserFormDialog from './UserFormDialog.vue'
import RoleFormDialog from './RoleFormDialog.vue'
import * as UserService from '@/data/UserService'
import * as RoleService from '@/data/RoleService'
import { toast } from 'vue-sonner'

const isClient = ref(true)
const activeTab = ref('users')
const searchKeyword = ref('')
const showUserDialog = ref(false)
const showRoleDialog = ref(false)
const editingUser = ref<any>(null)
const editingRole = ref<any>(null)

const users = ref(UserService.getAll())
const roles = ref(RoleService.getAll())

const filteredUsers = computed(() => {
  return UserService.query({
    keyword: searchKeyword.value,
  })
})

const filteredRoles = computed(() => {
  return RoleService.query({
    keyword: searchKeyword.value,
  })
})

const handleAddUser = () => {
  editingUser.value = null
  showUserDialog.value = true
}

const handleEditUser = (user: any) => {
  editingUser.value = user
  showUserDialog.value = true
}

const handleDeleteUser = (userId: string) => {
  const confirmed = confirm('确定要删除此用户吗？此操作不可撤销。')
  if (!confirmed) return

  const updatedUsers = users.value.filter(u => u.id !== userId)
  users.value = updatedUsers
  UserService.savePersisted(updatedUsers)
  toast.success('用户已删除')
}

const handleSaveUser = (userData: any) => {
  if (editingUser.value) {
    const index = users.value.findIndex(u => u.id === editingUser.value.id)
    if (index !== -1) {
      users.value[index] = { ...users.value[index], ...userData }
    }
    toast.success('用户信息已更新')
  } else {
    const newUser = {
      ...userData,
      id: `user-${Date.now()}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    users.value.push(newUser)
    toast.success('用户已创建')
  }
  UserService.savePersisted(users.value)
  showUserDialog.value = false
  editingUser.value = null
}

const handleAddRole = () => {
  editingRole.value = null
  showRoleDialog.value = true
}

const handleEditRole = (role: any) => {
  editingRole.value = role
  showRoleDialog.value = true
}

const handleDeleteRole = (roleId: string) => {
  const confirmed = confirm('确定要删除此角色吗？此操作不可撤销。')
  if (!confirmed) return

  const updatedRoles = roles.value.filter(r => r.id !== roleId)
  roles.value = updatedRoles
  RoleService.savePersisted(updatedRoles)
  toast.success('角色已删除')
}

const handleSaveRole = (roleData: any) => {
  if (editingRole.value) {
    const index = roles.value.findIndex(r => r.id === editingRole.value.id)
    if (index !== -1) {
      roles.value[index] = { ...roles.value[index], ...roleData }
    }
    toast.success('角色信息已更新')
  } else {
    const newRole = {
      ...roleData,
      id: `role-${Date.now()}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    roles.value.push(newRole)
    toast.success('角色已创建')
  }
  RoleService.savePersisted(roles.value)
  showRoleDialog.value = false
  editingRole.value = null
}

const handlePermissionChange = (roleId: string, updatedRole: any) => {
  const index = roles.value.findIndex(r => r.id === roleId)
  if (index !== -1) {
    roles.value[index] = updatedRole
    RoleService.savePersisted(roles.value)
    toast.success('权限已更新')
  }
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true
  })
})
</script>

<template>
  <div v-if="isClient" class="flex flex-col h-full min-h-0 bg-background">
    <PageHeader
      title="用户与权限管理"
      subtitle="管理系统用户、角色及其权限分配"
      :breadcrumb="[
        { label: '系统设置', href: './settings.html' },
        { label: '用户与权限管理' }
      ]"
    >
      <template #actions>
        <Button 
          v-if="activeTab === 'users'"
          class="gap-2"
          @click="handleAddUser"
        >
          <SafeIcon name="Plus" :size="16" />
          新增用户
        </Button>
        <Button 
          v-else
          class="gap-2"
          @click="handleAddRole"
        >
          <SafeIcon name="Plus" :size="16" />
          新增角色
        </Button>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0 page-body">
      <Tabs v-model="activeTab" class="w-full h-full flex flex-col">
        <TabsList class="w-full justify-start border-b border-border bg-transparent p-0 rounded-none h-auto">
          <TabsTrigger 
            value="users"
            class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-3"
          >
            <SafeIcon name="Users" :size="16" class="mr-2" />
            用户管理
          </TabsTrigger>
          <TabsTrigger 
            value="roles"
            class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-3"
          >
            <SafeIcon name="Shield" :size="16" class="mr-2" />
            角色管理
          </TabsTrigger>
        </TabsList>

        <TabsContent value="users" class="flex-1 overflow-y-auto min-h-0 mt-0 pt-4">
          <div class="space-y-4">
            <SearchBar 
              v-model="searchKeyword"
              placeholder="搜索用户名、邮箱或ID..."
            />
            <UserPermissionTable 
              :users="filteredUsers"
              @edit="handleEditUser"
              @delete="handleDeleteUser"
            />
          </div>
        </TabsContent>

        <TabsContent value="roles" class="flex-1 overflow-y-auto min-h-0 mt-0 pt-4">
          <div class="space-y-4">
            <SearchBar 
              v-model="searchKeyword"
              placeholder="搜索角色名称或代码..."
            />
            <RolePermissionMatrix 
              :roles="filteredRoles"
              @edit="handleEditRole"
              @delete="handleDeleteRole"
              @permission-change="handlePermissionChange"
            />
          </div>
        </TabsContent>
      </Tabs>
    </div>

    <UserFormDialog 
      v-if="showUserDialog"
      :user="editingUser"
      :roles="roles"
      @save="handleSaveUser"
      @close="showUserDialog = false"
    />

    <RoleFormDialog 
      v-if="showRoleDialog"
      :role="editingRole"
      @save="handleSaveRole"
      @close="showRoleDialog = false"
    />
  </div>
</template>

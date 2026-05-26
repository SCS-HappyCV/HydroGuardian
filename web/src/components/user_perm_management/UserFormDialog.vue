
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import SafeIcon from '@/components/common/SafeIcon.vue'
import * as ProjectService from '@/data/ProjectService'
import * as DatasetService from '@/data/DatasetService'

interface User {
  id?: string
  name: string
  email: string
  roleId: string
  projectId: string
  datasetId: string
  status: 'active' | 'disabled'
  avatarUrl?: string
}

const props = defineProps<{
  user: User | null
  roles: any[]
}>()

const emit = defineEmits<{
  (e: 'save', user: User): void
  (e: 'close'): void
}>()

const isOpen = ref(true)
const formData = ref<User>({
  name: '',
  email: '',
  roleId: '',
  projectId: '',
  datasetId: '',
  status: 'active',
})

const projects = ref(ProjectService.getAll())
const datasets = ref(DatasetService.getAll())

const isFormValid = computed(() => {
  return formData.value.name.trim() && 
         formData.value.email.trim() && 
         formData.value.roleId &&
         formData.value.projectId &&
         formData.value.datasetId
})

watch(() => props.user, (newUser) => {
  if (newUser) {
    formData.value = { ...newUser }
  } else {
    formData.value = {
      name: '',
      email: '',
      roleId: '',
      projectId: '',
      datasetId: '',
      status: 'active',
    }
  }
}, { immediate: true })

const handleSave = () => {
  if (!isFormValid.value) return
  emit('save', formData.value)
}

const handleClose = () => {
  isOpen.value = false
  emit('close')
}
</script>

<template>
  <Dialog v-model:open="isOpen" @update:open="handleClose">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <SafeIcon name="User" :size="20" />
          {{ user ? '编辑用户' : '新增用户' }}
        </DialogTitle>
      </DialogHeader>

      <div class="space-y-4 py-4">
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-2">
            <Label for="name" class="text-label">用户名 *</Label>
            <Input 
              id="name"
              v-model="formData.name"
              placeholder="输入用户名"
              class="bg-muted/40"
            />
          </div>
          <div class="space-y-2">
            <Label for="email" class="text-label">邮箱 *</Label>
            <Input 
              id="email"
              v-model="formData.email"
              type="email"
              placeholder="输入邮箱地址"
              class="bg-muted/40"
            />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-2">
            <Label for="role" class="text-label">角色 *</Label>
            <Select v-model="formData.roleId">
              <SelectTrigger id="role" class="bg-muted/40">
                <SelectValue placeholder="选择角色" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem 
                  v-for="role in roles"
                  :key="role.id"
                  :value="role.id"
                >
                  {{ role.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label for="status" class="text-label">状态 *</Label>
            <Select v-model="formData.status">
              <SelectTrigger id="status" class="bg-muted/40">
                <SelectValue placeholder="选择状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">活跃</SelectItem>
                <SelectItem value="disabled">禁用</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-2">
            <Label for="project" class="text-label">项目 *</Label>
            <Select v-model="formData.projectId">
              <SelectTrigger id="project" class="bg-muted/40">
                <SelectValue placeholder="选择项目" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem 
                  v-for="project in projects"
                  :key="project.id"
                  :value="project.id"
                >
                  {{ project.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label for="dataset" class="text-label">数据集 *</Label>
            <Select v-model="formData.datasetId">
              <SelectTrigger id="dataset" class="bg-muted/40">
                <SelectValue placeholder="选择数据集" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem 
                  v-for="dataset in datasets"
                  :key="dataset.id"
                  :value="dataset.id"
                >
                  {{ dataset.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <DialogFooter class="flex gap-2 justify-end">
        <Button variant="outline" @click="handleClose">
          取消
        </Button>
        <Button 
          :disabled="!isFormValid"
          @click="handleSave"
        >
          {{ user ? '更新' : '创建' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

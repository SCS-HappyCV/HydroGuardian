
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
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import SafeIcon from '@/components/common/SafeIcon.vue'

interface Role {
  id?: string
  name: string
  code: string
  description: string
  permissionCount?: number
  isSystem?: boolean
}

const props = defineProps<{
  role: Role | null
}>()

const emit = defineEmits<{
  (e: 'save', role: Role): void
  (e: 'close'): void
}>()

const isOpen = ref(true)
const formData = ref<Role>({
  name: '',
  code: '',
  description: '',
  permissionCount: 0,
  isSystem: false,
})

const isFormValid = computed(() => {
  return formData.value.name.trim() && 
         formData.value.code.trim() &&
         formData.value.description.trim()
})

watch(() => props.role, (newRole) => {
  if (newRole) {
    formData.value = { ...newRole }
  } else {
    formData.value = {
      name: '',
      code: '',
      description: '',
      permissionCount: 0,
      isSystem: false,
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
          <SafeIcon name="Shield" :size="20" />
          {{ role ? '编辑角色' : '新增角色' }}
        </DialogTitle>
      </DialogHeader>

      <div class="space-y-4 py-4">
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-2">
            <Label for="name" class="text-label">角色名称 *</Label>
            <Input 
              id="name"
              v-model="formData.name"
              placeholder="输入角色名称"
              class="bg-muted/40"
            />
          </div>
          <div class="space-y-2">
            <Label for="code" class="text-label">角色代码 *</Label>
            <Input 
              id="code"
              v-model="formData.code"
              placeholder="输入角色代码（英文）"
              class="bg-muted/40"
            />
          </div>
        </div>

        <div class="space-y-2">
          <Label for="description" class="text-label">角色描述 *</Label>
          <Textarea 
            id="description"
            v-model="formData.description"
            placeholder="输入角色描述"
            class="bg-muted/40 min-h-[100px]"
          />
        </div>

        <div class="p-3 bg-muted/30 rounded-lg border border-border/50">
          <p class="text-xs text-muted-foreground">
            <SafeIcon name="Info" :size="12" class="inline mr-1" />
            权限分配将在角色创建后通过权限矩阵进行配置
          </p>
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
          {{ role ? '更新' : '创建' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

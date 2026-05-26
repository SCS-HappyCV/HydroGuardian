
<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  attachments: File[]
}>()

const emit = defineEmits<{
  (e: 'add', file: File): void
  (e: 'remove', index: number): void
}>()

const isDragging = ref(false)
const fileInputRef = ref<HTMLInputElement>()

const handleDragOver = (e: DragEvent) => {
  e.preventDefault()
  isDragging.value = true
}

const handleDragLeave = () => {
  isDragging.value = false
}

const handleDrop = (e: DragEvent) => {
  e.preventDefault()
  isDragging.value = false
  
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    emit('add', files[0])
  }
}

const handleFileSelect = (e: Event) => {
  const input = e.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    emit('add', input.files[0])
    input.value = ''
  }
}

const handleClick = () => {
  fileInputRef.value?.click()
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}
</script>

<template>
  <div class="space-y-3">
    <!-- 上传区域 -->
    <div
      :class="[
        'border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer',
        isDragging 
          ? 'border-primary bg-primary/5' 
          : 'border-border/50 bg-muted/10 hover:border-primary/50 hover:bg-primary/5'
      ]"
      @dragover="handleDragOver"
      @dragleave="handleDragLeave"
      @drop="handleDrop"
      @click="handleClick"
    >
      <input
        ref="fileInputRef"
        type="file"
        multiple
        accept="image/*,.pdf,.doc,.docx,.xls,.xlsx"
        class="hidden"
        @change="handleFileSelect"
      />
      
      <div class="space-y-2">
        <SafeIcon 
          name="Upload" 
          :size="32" 
          class="mx-auto text-muted-foreground/50"
        />
        <div>
          <p class="text-sm font-medium text-foreground">
            拖拽文件到此或点击选择
          </p>
          <p class="text-xs text-muted-foreground mt-1">
            支持图片、PDF、Office 文档等格式，单个文件不超过 50MB
          </p>
        </div>
      </div>
    </div>

    <!-- 已上传文件列表 -->
    <div v-if="attachments.length > 0" class="space-y-2">
      <p class="text-sm font-medium text-foreground">已上传文件（{{ attachments.length }}）</p>
      <div class="space-y-1">
        <div 
          v-for="(file, index) in attachments"
          :key="index"
          class="flex items-center justify-between gap-2 p-2 bg-muted/20 border border-border/30 rounded"
        >
          <div class="flex items-center gap-2 flex-1 min-w-0">
            <SafeIcon 
              :name="file.type.startsWith('image/') ? 'Image' : 'File'"
              :size="16"
              class="text-primary shrink-0"
            />
            <div class="flex-1 min-w-0">
              <p class="text-sm text-foreground truncate">{{ file.name }}</p>
              <p class="text-xs text-muted-foreground">{{ formatFileSize(file.size) }}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            class="h-8 w-8 shrink-0 text-destructive hover:text-destructive hover:bg-destructive/10"
            @click="emit('remove', index)"
          >
            <SafeIcon name="X" :size="16" />
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

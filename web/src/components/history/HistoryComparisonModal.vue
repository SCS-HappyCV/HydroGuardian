
<script setup lang="ts">
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'confirm'): void
}>()

const handleConfirm = () => {
  emit('confirm')
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="props.open" @update:open="(val) => emit('update:open', val)">
    <DialogContent class="max-w-md">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <SafeIcon name="GitCompare" :size="20" class="text-primary" />
          确认对比
        </DialogTitle>
        <DialogDescription>
          您已选择两个任务进行对比。系统将展示两次执行结果的差异，包括新增、消失和变化的风险点。
        </DialogDescription>
      </DialogHeader>

      <div class="py-4 space-y-3">
        <div class="p-3 bg-muted/30 rounded-lg border border-border">
          <p class="text-xs text-muted-foreground mb-1">对比将包含：</p>
          <ul class="text-xs text-card-foreground space-y-1 ml-4">
            <li>• 新增风险点</li>
            <li>• 消失的风险点</li>
            <li>• 风险等级变化</li>
            <li>• 地理位置对比</li>
          </ul>
        </div>
      </div>

      <DialogFooter class="flex gap-2">
        <Button variant="outline" @click="() => emit('update:open', false)">
          取消
        </Button>
        <Button @click="handleConfirm" class="gap-2">
          <SafeIcon name="Check" :size="16" />
          开始对比
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

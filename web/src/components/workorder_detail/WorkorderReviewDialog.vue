
<script setup lang="ts">
import { ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  orderId: string
}>()

const emit = defineEmits<{
  (e: 'submit', decision: 'approved' | 'rejected', comment: string): void
  (e: 'cancel'): void
}>()

const decision = ref<'approved' | 'rejected'>('approved')
const comment = ref('')
const evidenceNote = ref('')

const handleSubmit = () => {
  if (!comment.trim()) {
    toast.error('请填写复核意见')
    return
  }

  emit('submit', decision.value, comment.value)
}

const handleCancel = () => {
  emit('cancel')
}
</script>

<template>
  <Dialog open @update:open="(open) => !open && handleCancel()">
    <DialogContent class="max-w-2xl flex flex-col max-h-[80vh]">
      <DialogHeader class="flex-shrink-0">
        <DialogTitle class="text-xl">工单复核</DialogTitle>
        <DialogDescription>
          请审核处理结果并提交复核意见
        </DialogDescription>
      </DialogHeader>

      <div class="flex-1 overflow-y-auto min-h-0 space-y-4 py-4">
        <!-- 复核决定 -->
        <div class="space-y-3">
          <Label class="text-label">复核决定</Label>
          <RadioGroup v-model="decision" class="space-y-2">
            <div class="flex items-center space-x-2">
              <RadioGroupItem value="approved" id="approved" />
              <Label for="approved" class="font-normal cursor-pointer flex items-center gap-2">
                <SafeIcon name="CheckCircle2" :size="16" class="text-[hsl(var(--success))]" />
                通过
              </Label>
            </div>
            <div class="flex items-center space-x-2">
              <RadioGroupItem value="rejected" id="rejected" />
              <Label for="rejected" class="font-normal cursor-pointer flex items-center gap-2">
                <SafeIcon name="XCircle" :size="16" class="text-destructive" />
                驳回
              </Label>
            </div>
          </RadioGroup>
        </div>

        <!-- 复核意见 -->
        <div class="space-y-2">
          <Label for="comment" class="text-label">复核意见</Label>
          <Textarea
            id="comment"
            v-model="comment"
            placeholder="请详细说明复核结论和建议..."
            class="min-h-[120px] bg-card/50 border-border focus:ring-1 focus:ring-primary"
          />
          <p class="text-xs text-muted-foreground">{{ comment.length }} / 1000 字符</p>
        </div>

        <!-- 证据说明 -->
        <div class="space-y-2">
          <Label for="evidence" class="text-label">证据说明</Label>
          <Textarea
            id="evidence"
            v-model="evidenceNote"
            placeholder="补充处理前后对比、现场照片等证据信息..."
            class="min-h-[100px] bg-card/50 border-border focus:ring-1 focus:ring-primary"
          />
          <p class="text-xs text-muted-foreground">{{ evidenceNote.length }} / 500 字符</p>
        </div>
      </div>

      <DialogFooter class="flex-shrink-0 gap-2 pt-4 border-t border-border/30">
        <Button variant="outline" @click="handleCancel">
          取消
        </Button>
        <Button @click="handleSubmit" class="gap-2">
          <SafeIcon name="CheckCircle2" :size="16" />
          提交复核
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

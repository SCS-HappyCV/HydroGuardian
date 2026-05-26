
<script setup lang="ts">
import { Textarea } from '@/components/ui/textarea'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const handleInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
}

const charCount = computed(() => props.modelValue.length)
const maxChars = 500
</script>

<template>
  <div class="surface-base card-padding space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="text-item-title flex items-center gap-2">
        <SafeIcon name="MessageSquare" :size="18" class="text-primary" />
        任务描述
      </h3>
      <span class="text-caption text-muted-foreground">
        {{ charCount }} / {{ maxChars }}
      </span>
    </div>

    <Textarea
      :value="modelValue"
      @input="handleInput"
      placeholder="请输入任务描述，例如：检查滨海泵站周边夜间异常水位波动并生成风险清单"
      class="min-h-[120px] bg-muted/20 border-border focus:border-primary resize-none"
      :maxlength="maxChars"
    />

    <div class="flex items-start gap-2 text-xs text-muted-foreground bg-muted/20 p-2 rounded-md">
      <SafeIcon name="Lightbulb" :size="14" class="mt-0.5 flex-shrink-0" />
      <p>提示：使用具体的地点、时间和检查重点描述，系统将自动解析任务参数并推荐最优执行方案。</p>
    </div>
  </div>
</template>


<script setup lang="ts">
import { Textarea } from '@/components/ui/textarea'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

function handleUpdate(value: string | number) {
  emit('update:modelValue', String(value))
}

const charCount = computed(() => props.modelValue.length)
const maxChars = 500
</script>

<template>
  <section class="rounded-2xl border border-white/[0.08] bg-card/60 p-5 shadow-card">
    <div class="flex items-center justify-between">
      <h3 class="text-item-title flex items-center gap-2">
        <span class="grid h-7 w-7 place-items-center rounded-lg bg-primary/10 text-xs font-semibold text-primary">1</span>
        描述巡查目标
      </h3>
      <span class="text-caption text-muted-foreground">
        {{ charCount }} / {{ maxChars }}
      </span>
    </div>

    <Textarea
      :model-value="modelValue"
      @update:model-value="handleUpdate"
      placeholder="例如：筛查近水扰动区域，重点识别细长沟渠并排除道路，结合前后时相变化按风险高低排序"
      class="mt-4 min-h-[124px] resize-y border-border bg-muted/20 text-[15px] leading-6 focus:border-primary"
      :maxlength="maxChars"
    />
    <p class="mt-2 text-xs text-muted-foreground">说清检查对象、空间范围和判断重点即可，Agent 会自动组织分析步骤。</p>
  </section>
</template>

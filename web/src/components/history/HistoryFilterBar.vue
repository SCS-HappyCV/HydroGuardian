
<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'

interface FilterOption {
  value: string
  label: string
}

interface Filters {
  timeRange: string
  zoneId: string
  taskType: string
}

const props = defineProps<{
  modelValue: Filters
  timeRangeOptions: FilterOption[]
  zoneOptions: FilterOption[]
  taskTypeOptions: FilterOption[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: Filters): void
}>()

const localFilters = ref<Filters>({ ...props.modelValue })

watch(() => props.modelValue, (newVal) => {
  localFilters.value = { ...newVal }
})

const handleUpdate = (key: keyof Filters, value: string) => {
  localFilters.value[key] = value
  emit('update:modelValue', { ...localFilters.value })
}

const handleReset = () => {
  const resetFilters: Filters = {
    timeRange: 'all',
    zoneId: 'all',
    taskType: 'all'
  }
  localFilters.value = resetFilters
  emit('update:modelValue', resetFilters)
  toast.success('筛选条件已重置')
}
</script>

<template>
  <div class="surface-base card-padding flex flex-wrap items-center gap-4">
    <div class="flex items-center gap-2">
      <label class="text-label whitespace-nowrap">时间范围</label>
      <Select :model-value="localFilters.timeRange" @update:model-value="(val) => handleUpdate('timeRange', val)">
        <SelectTrigger class="w-[140px] h-9 bg-card/50">
          <SelectValue placeholder="选择时间范围" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in timeRangeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div class="flex items-center gap-2">
      <label class="text-label whitespace-nowrap">区域</label>
      <Select :model-value="localFilters.zoneId" @update:model-value="(val) => handleUpdate('zoneId', val)">
        <SelectTrigger class="w-[140px] h-9 bg-card/50">
          <SelectValue placeholder="选择区域" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in zoneOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div class="flex items-center gap-2">
      <label class="text-label whitespace-nowrap">任务类型</label>
      <Select :model-value="localFilters.taskType" @update:model-value="(val) => handleUpdate('taskType', val)">
        <SelectTrigger class="w-[140px] h-9 bg-card/50">
          <SelectValue placeholder="选择任务类型" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in taskTypeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <Button 
      variant="ghost" 
      size="sm" 
      class="h-9 px-3 text-muted-foreground hover:text-foreground ml-auto"
      @click="handleReset"
    >
      <SafeIcon name="RotateCcw" :size="14" class="mr-2" />
      重置
    </Button>
  </div>
</template>

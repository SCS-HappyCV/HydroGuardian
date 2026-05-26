
<script setup lang="ts">
import type { ZoneData } from '@/data/ZoneData'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  zoneId: string
  priority: 'low' | 'medium' | 'high'
  sampleId: string
  zones: ZoneData[]
}>()

const emit = defineEmits<{
  (e: 'update:zoneId', value: string): void
  (e: 'update:priority', value: 'low' | 'medium' | 'high'): void
  (e: 'update:sampleId', value: string): void
  (e: 'change'): void
}>()

const handleZoneChange = (value: string) => {
  emit('update:zoneId', value)
  emit('change')
}

const handlePriorityChange = (value: string) => {
  emit('update:priority', value as 'low' | 'medium' | 'high')
  emit('change')
}

const handleSampleChange = (value: string) => {
  emit('update:sampleId', value)
  emit('change')
}

const priorityLabels = {
  low: '低优先级',
  medium: '中优先级',
  high: '高优先级'
}

const priorityIcons = {
  low: 'ChevronDown',
  medium: 'Minus',
  high: 'ChevronUp'
}
</script>

<template>
  <div class="surface-base card-padding space-y-4">
    <h3 class="text-item-title flex items-center gap-2">
      <SafeIcon name="Settings" :size="18" class="text-accent" />
      参数配置
    </h3>

    <div class="space-y-3">
      <div class="space-y-2">
        <Label class="text-label">工作区域</Label>
        <Select :model-value="zoneId" @update:model-value="handleZoneChange">
          <SelectTrigger class="bg-muted/20 border-border">
            <SelectValue placeholder="选择工作区域" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem 
              v-for="zone in zones" 
              :key="zone.id" 
              :value="zone.id"
            >
              {{ zone.name }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div class="space-y-2">
        <Label class="text-label">优先级</Label>
        <Select :model-value="priority" @update:model-value="handlePriorityChange">
          <SelectTrigger class="bg-muted/20 border-border">
            <SelectValue placeholder="选择优先级" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="low">
              <div class="flex items-center gap-2">
                <SafeIcon name="ChevronDown" :size="14" />
                低优先级
              </div>
            </SelectItem>
            <SelectItem value="medium">
              <div class="flex items-center gap-2">
                <SafeIcon name="Minus" :size="14" />
                中优先级
              </div>
            </SelectItem>
            <SelectItem value="high">
              <div class="flex items-center gap-2">
                <SafeIcon name="ChevronUp" :size="14" />
                高优先级
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div class="space-y-2">
        <Label class="text-label">样本数据（可选）</Label>
        <Select :model-value="sampleId" @update:model-value="handleSampleChange">
          <SelectTrigger class="bg-muted/20 border-border">
            <SelectValue placeholder="选择或跳过" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">
              <span class="text-muted-foreground">不使用样本</span>
            </SelectItem>
            <SelectItem value="sample-001">样本 001 - 滨海夜巡</SelectItem>
            <SelectItem value="sample-002">样本 002 - 西港工业</SelectItem>
            <SelectItem value="sample-003">样本 003 - 北岸排水</SelectItem>
            <SelectItem value="sample-004">样本 004 - 中心城区</SelectItem>
            <SelectItem value="sample-005">样本 005 - 南堤闸门</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>

    <div class="pt-2 border-t border-border/50 mt-4">
      <div class="text-[10px] text-muted-foreground space-y-1">
        <p>💡 <strong>参数说明：</strong></p>
        <p>• 工作区域：任务执行的地理范围</p>
        <p>• 优先级：影响任务队列排序和资源分配</p>
        <p>• 样本数据：可选的参考数据集</p>
      </div>
    </div>
  </div>
</template>

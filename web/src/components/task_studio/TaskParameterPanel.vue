
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

</script>

<template>
  <div class="rounded-xl border border-white/[0.07] bg-black/10 p-3">
    <h3 class="mb-3 flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="Settings" :size="14" class="text-accent" />任务设置</h3>

    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
      <div class="space-y-1.5">
        <Label class="text-[11px]">工作区域</Label>
        <Select :model-value="zoneId" @update:model-value="handleZoneChange">
          <SelectTrigger class="h-9 border-border bg-muted/20">
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

      <div class="space-y-1.5">
        <Label class="text-[11px]">优先级</Label>
        <Select :model-value="priority" @update:model-value="handlePriorityChange">
          <SelectTrigger class="h-9 border-border bg-muted/20">
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

      <div class="space-y-1.5 sm:col-span-2 lg:col-span-1">
        <Label class="text-[11px]">样本数据（可选）</Label>
        <Select :model-value="sampleId" @update:model-value="handleSampleChange">
          <SelectTrigger class="h-9 border-border bg-muted/20">
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

  </div>
</template>

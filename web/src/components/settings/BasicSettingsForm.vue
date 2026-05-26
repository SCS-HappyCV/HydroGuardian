
<script setup lang="ts">
import { ref, computed } from 'vue'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { SettingData } from '@/data/SettingData'

const props = defineProps<{
  settings: SettingData[]
}>()

const emit = defineEmits<{
  (e: 'update', settings: SettingData[]): void
}>()

const formData = ref({
  systemName: props.settings.find(s => s.key === 'systemName')?.value || 'HydroGuardian',
  defaultTimeRange: props.settings.find(s => s.key === 'defaultTimeRange')?.value || '24h'
})

const handleSystemNameChange = (value: string) => {
  formData.value.systemName = value
  const updated = props.settings.map(s => 
    s.key === 'systemName' ? { ...s, value } : s
  )
  emit('update', updated)
}

const handleTimeRangeChange = (value: string) => {
  formData.value.defaultTimeRange = value
  const updated = props.settings.map(s => 
    s.key === 'defaultTimeRange' ? { ...s, value } : s
  )
  emit('update', updated)
}
</script>

<template>
  <div class="form-section space-y-6">
    <div class="space-y-2">
      <Label for="systemName" class="text-label">系统名称</Label>
      <Input 
        id="systemName"
        :value="formData.systemName"
        @input="(e) => handleSystemNameChange((e.target as HTMLInputElement).value)"
        placeholder="输入系统名称"
        class="bg-card/50 border-border focus:ring-1 focus:ring-primary"
      />
      <p class="text-caption text-muted-foreground">系统在全局导航栏中显示的名称</p>
    </div>

    <div class="space-y-2">
      <Label for="defaultTimeRange" class="text-label">默认时间范围</Label>
      <Select :model-value="formData.defaultTimeRange" @update:model-value="handleTimeRangeChange">
        <SelectTrigger id="defaultTimeRange" class="bg-card/50 border-border">
          <SelectValue placeholder="选择默认时间范围" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="1h">最近 1 小时</SelectItem>
          <SelectItem value="6h">最近 6 小时</SelectItem>
          <SelectItem value="24h">最近 24 小时</SelectItem>
          <SelectItem value="7d">最近 7 天</SelectItem>
          <SelectItem value="30d">最近 30 天</SelectItem>
        </SelectContent>
      </Select>
      <p class="text-caption text-muted-foreground">新打开页面时的默认数据查询时间范围</p>
    </div>

    <div class="surface-base/50 border border-border/50 rounded-lg p-4 space-y-2">
      <p class="text-sm font-medium text-foreground">系统版本信息</p>
      <div class="grid grid-cols-2 gap-4 text-xs text-muted-foreground">
        <div>
          <p class="text-caption">当前版本</p>
          <p class="text-foreground font-mono">v2.1.0</p>
        </div>
        <div>
          <p class="text-caption">最后更新</p>
          <p class="text-foreground font-mono">2026-05-25</p>
        </div>
      </div>
    </div>
  </div>
</template>

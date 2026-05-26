
<script setup lang="ts">
import { ref } from 'vue'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'
import type { SettingData } from '@/data/SettingData'

const props = defineProps<{
  settings: SettingData[]
}>()

const emit = defineEmits<{
  (e: 'update', settings: SettingData[]): void
}>()

const dataSources = ref([
  {
    id: 'ds-001',
    name: '实时巡检数据集',
    type: 'GIS',
    status: 'connected',
    lastSync: '2026-05-25 07:45:00',
    recordCount: 15234
  },
  {
    id: 'ds-002',
    name: '历史风险数据集',
    type: 'Manual Upload',
    status: 'connected',
    lastSync: '2026-05-25 06:30:00',
    recordCount: 8921
  },
  {
    id: 'ds-003',
    name: '传感器汇聚数据集',
    type: 'Sensor Network',
    status: 'syncing',
    lastSync: '2026-05-25 07:50:00',
    recordCount: 42156
  }
])

const testingId = ref<string | null>(null)

const handleTestConnection = (id: string) => {
  testingId.value = id
  setTimeout(() => {
    testingId.value = null
    toast.success('数据源连接测试成功')
  }, 1500)
}

const getStatusBadgeClass = (status: string) => {
  switch (status) {
    case 'connected':
      return 'bg-[hsl(var(--success))]/20 text-[hsl(var(--success))] border-[hsl(var(--success))]/30'
    case 'syncing':
      return 'bg-primary/20 text-primary border-primary/30'
    case 'error':
      return 'bg-destructive/20 text-destructive border-destructive/30'
    default:
      return 'bg-muted/20 text-muted-foreground border-muted/30'
  }
}

const getStatusLabel = (status: string) => {
  switch (status) {
    case 'connected':
      return '已连接'
    case 'syncing':
      return '同步中'
    case 'error':
      return '连接错误'
    default:
      return '未知'
  }
}
</script>

<template>
  <div class="form-section space-y-6">
    <div class="space-y-3">
      <h3 class="text-section-title">已配置的数据源</h3>
      <div class="space-y-3">
        <div 
          v-for="source in dataSources" 
          :key="source.id"
          class="surface-base card-padding space-y-3 border border-border/50"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 space-y-2">
              <div class="flex items-center gap-3">
                <h4 class="text-item-title">{{ source.name }}</h4>
                <Badge 
                  variant="outline" 
                  :class="getStatusBadgeClass(source.status)"
                >
                  <div 
                    v-if="source.status === 'syncing'"
                    class="w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse"
                  />
                  {{ getStatusLabel(source.status) }}
                </Badge>
              </div>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs text-muted-foreground">
                <div>
                  <p class="text-caption">数据源类型</p>
                  <p class="text-foreground font-medium">{{ source.type }}</p>
                </div>
                <div>
                  <p class="text-caption">记录数</p>
                  <p class="text-foreground font-medium">{{ source.recordCount.toLocaleString() }}</p>
                </div>
                <div class="col-span-2">
                  <p class="text-caption">最后同步</p>
                  <p class="text-foreground font-mono text-[10px]">{{ source.lastSync }}</p>
                </div>
              </div>
            </div>

            <Button 
              variant="outline" 
              size="sm"
              @click="handleTestConnection(source.id)"
              :disabled="testingId === source.id"
              class="gap-2 whitespace-nowrap"
            >
              <SafeIcon 
                v-if="testingId === source.id"
                name="Loader2" 
                :size="14" 
                class="animate-spin"
              />
              <SafeIcon v-else name="Zap" :size="14" />
              {{ testingId === source.id ? '测试中...' : '测试连接' }}
            </Button>
          </div>
        </div>
      </div>
    </div>

    <div class="surface-base/50 border border-border/50 rounded-lg p-4 space-y-3">
      <p class="text-sm font-medium text-foreground">数据同步设置</p>
      <div class="space-y-3">
        <div class="space-y-2">
          <Label for="refreshInterval" class="text-label">数据刷新间隔</Label>
          <Input 
            id="refreshInterval"
            type="text"
            value="5分钟"
            disabled
            class="bg-muted/30 border-border text-muted-foreground cursor-not-allowed"
          />
          <p class="text-caption text-muted-foreground">系统自动同步数据源的时间间隔</p>
        </div>
      </div>
    </div>
  </div>
</template>

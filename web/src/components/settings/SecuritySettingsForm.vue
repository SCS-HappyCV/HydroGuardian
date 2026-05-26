
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

const showApiKey = ref(false)
const apiKeyValue = ref(props.settings.find(s => s.key === 'apiKeyPrimary')?.value || 'hgk-live-81a2-xxxx')

const apiKeys = ref([
  {
    id: 'key-001',
    name: '主 API Key',
    key: 'hgk-live-81a2-xxxx',
    status: 'active',
    createdAt: '2026-03-01',
    lastUsed: '2026-05-25 08:15:00'
  },
  {
    id: 'key-002',
    name: '备用 API Key',
    key: 'hgk-backup-b3c4-yyyy',
    status: 'inactive',
    createdAt: '2026-04-15',
    lastUsed: '-'
  }
])

const handleToggleApiKeyVisibility = () => {
  showApiKey.value = !showApiKey.value
}

const handleCopyApiKey = () => {
  navigator.clipboard.writeText(apiKeyValue.value)
  toast.success('API Key 已复制到剪贴板')
}

const handleRegenerateKey = () => {
  toast.info('API Key 重新生成功能需要二次确认，请在系统管理员处理')
}

const handleRevokeKey = (id: string) => {
  toast.warning('API Key 已撤销，该密钥将立即失效')
}
</script>

<template>
  <div class="form-section space-y-6">
    <div class="space-y-3">
      <h3 class="text-section-title">API 密钥管理</h3>
      
      <div class="space-y-3">
        <div 
          v-for="key in apiKeys" 
          :key="key.id"
          class="surface-base card-padding space-y-3 border border-border/50"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 space-y-2">
              <div class="flex items-center gap-3">
                <h4 class="text-item-title">{{ key.name }}</h4>
                <Badge 
                  :variant="key.status === 'active' ? 'default' : 'secondary'"
                  :class="key.status === 'active' ? 'bg-[hsl(var(--success))]/20 text-[hsl(var(--success))] border-[hsl(var(--success))]/30' : ''"
                >
                  {{ key.status === 'active' ? '活跃' : '停用' }}
                </Badge>
              </div>
              <div class="grid grid-cols-2 md:grid-cols-3 gap-4 text-xs text-muted-foreground">
                <div>
                  <p class="text-caption">创建时间</p>
                  <p class="text-foreground font-mono">{{ key.createdAt }}</p>
                </div>
                <div>
                  <p class="text-caption">最后使用</p>
                  <p class="text-foreground font-mono">{{ key.lastUsed }}</p>
                </div>
                <div>
                  <p class="text-caption">密钥值</p>
                  <p class="text-foreground font-mono">{{ key.key }}</p>
                </div>
              </div>
            </div>

            <div v-if="key.status === 'active'" class="flex gap-2">
              <Button 
                variant="outline" 
                size="sm"
                @click="handleRegenerateKey"
                class="gap-2"
              >
                <SafeIcon name="RefreshCw" :size="14" />
                重新生成
              </Button>
            </div>
            <div v-else>
              <Button 
                variant="outline" 
                size="sm"
                @click="() => handleRevokeKey(key.id)"
                class="gap-2 text-destructive hover:text-destructive"
              >
                <SafeIcon name="Trash2" :size="14" />
                撤销
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="surface-base/50 border border-border/50 rounded-lg p-4 space-y-3">
      <p class="text-sm font-medium text-foreground">安全策略</p>
      <div class="space-y-3 text-xs text-muted-foreground">
        <div class="flex items-start gap-2">
          <SafeIcon name="CheckCircle2" :size="14" class="text-[hsl(var(--success))] mt-0.5 flex-shrink-0" />
          <span>所有 API 请求均通过 HTTPS 加密传输</span>
        </div>
        <div class="flex items-start gap-2">
          <SafeIcon name="CheckCircle2" :size="14" class="text-[hsl(var(--success))] mt-0.5 flex-shrink-0" />
          <span>API Key 采用 AES-256 加密存储</span>
        </div>
        <div class="flex items-start gap-2">
          <SafeIcon name="CheckCircle2" :size="14" class="text-[hsl(var(--success))] mt-0.5 flex-shrink-0" />
          <span>所有操作记录完整审计日志</span>
        </div>
        <div class="flex items-start gap-2">
          <SafeIcon name="AlertCircle" :size="14" class="text-[hsl(var(--warning))] mt-0.5 flex-shrink-0" />
          <span>建议每 90 天轮换一次 API Key</span>
        </div>
      </div>
    </div>

    <div class="surface-base/50 border border-border/50 rounded-lg p-4 space-y-3">
      <p class="text-sm font-medium text-foreground">访问控制</p>
      <div class="space-y-2 text-xs text-muted-foreground">
        <p>当前用户权限级别：<span class="text-foreground font-medium">系统管理员</span></p>
        <p>可访问的功能模块：<span class="text-foreground font-medium">全部</span></p>
        <p>数据访问范围：<span class="text-foreground font-medium">全部项目和数据集</span></p>
      </div>
    </div>
  </div>
</template>

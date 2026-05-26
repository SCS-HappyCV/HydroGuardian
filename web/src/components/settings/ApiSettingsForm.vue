
<script setup lang="ts">
import { ref } from 'vue'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'
import type { SettingData } from '@/data/SettingData'

const props = defineProps<{
  settings: SettingData[]
}>()

const emit = defineEmits<{
  (e: 'update', settings: SettingData[]): void
}>()

const formData = ref({
  gisServiceUrl: props.settings.find(s => s.key === 'gisServiceUrl')?.value || 'https://api.hydroguardian.cn/gis',
  modelServiceUrl: props.settings.find(s => s.key === 'modelServiceUrl')?.value || 'https://api.hydroguardian.cn/model'
})

const testingService = ref<string | null>(null)

const handleUrlChange = (key: string, value: string) => {
  formData.value[key as keyof typeof formData.value] = value
  const updated = props.settings.map(s => 
    s.key === key ? { ...s, value } : s
  )
  emit('update', updated)
}

const handleTestService = (service: string) => {
  testingService.value = service
  setTimeout(() => {
    testingService.value = null
    toast.success(`${service === 'gis' ? 'GIS' : '模型'}服务连接测试成功`)
  }, 1500)
}
</script>

<template>
  <div class="form-section space-y-6">
    <div class="space-y-2">
      <Label for="gisServiceUrl" class="text-label">GIS 服务地址</Label>
      <div class="flex gap-2">
        <Input 
          id="gisServiceUrl"
          :value="formData.gisServiceUrl"
          @input="(e) => handleUrlChange('gisServiceUrl', (e.target as HTMLInputElement).value)"
          placeholder="输入 GIS 服务 URL"
          class="bg-card/50 border-border focus:ring-1 focus:ring-primary flex-1"
        />
        <Button 
          variant="outline" 
          size="icon"
          @click="() => handleTestService('gis')"
          :disabled="testingService === 'gis'"
          class="gap-2"
        >
          <SafeIcon 
            v-if="testingService === 'gis'"
            name="Loader2" 
            :size="16" 
            class="animate-spin"
          />
          <SafeIcon v-else name="Zap" :size="16" />
        </Button>
      </div>
      <p class="text-caption text-muted-foreground">用于地图渲染和空间分析的 GIS 服务地址</p>
    </div>

    <div class="space-y-2">
      <Label for="modelServiceUrl" class="text-label">模型服务地址</Label>
      <div class="flex gap-2">
        <Input 
          id="modelServiceUrl"
          :value="formData.modelServiceUrl"
          @input="(e) => handleUrlChange('modelServiceUrl', (e.target as HTMLInputElement).value)"
          placeholder="输入模型服务 URL"
          class="bg-card/50 border-border focus:ring-1 focus:ring-primary flex-1"
        />
        <Button 
          variant="outline" 
          size="icon"
          @click="() => handleTestService('model')"
          :disabled="testingService === 'model'"
          class="gap-2"
        >
          <SafeIcon 
            v-if="testingService === 'model'"
            name="Loader2" 
            :size="16" 
            class="animate-spin"
          />
          <SafeIcon v-else name="Zap" :size="16" />
        </Button>
      </div>
      <p class="text-caption text-muted-foreground">用于风险分析和任务执行的 AI 模型服务地址</p>
    </div>

    <div class="surface-base/50 border border-border/50 rounded-lg p-4 space-y-3">
      <p class="text-sm font-medium text-foreground">服务状态</p>
      <div class="grid grid-cols-2 gap-4 text-xs">
        <div class="space-y-1">
          <p class="text-caption text-muted-foreground">GIS 服务</p>
          <div class="flex items-center gap-2">
            <div class="w-2 h-2 rounded-full bg-[hsl(var(--success))] shadow-[0_0_8px_hsl(var(--success) / 0.5)]" />
            <span class="text-foreground font-medium">正常运行</span>
          </div>
        </div>
        <div class="space-y-1">
          <p class="text-caption text-muted-foreground">模型服务</p>
          <div class="flex items-center gap-2">
            <div class="w-2 h-2 rounded-full bg-[hsl(var(--success))] shadow-[0_0_8px_hsl(var(--success) / 0.5)]" />
            <span class="text-foreground font-medium">正常运行</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

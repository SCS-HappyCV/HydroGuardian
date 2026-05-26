
<script setup lang="ts">
import type { TaskTemplateData } from '@/data/TaskTemplateData'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  templates: TaskTemplateData[]
  selectedTemplateId: string
}>()

const emit = defineEmits<{
  (e: 'select', templateId: string): void
}>()

const categoryLabels: Record<string, string> = {
  inspection: '日常巡检',
  review: '复核评估',
  emergency: '应急响应'
}

const categoryIcons: Record<string, string> = {
  inspection: 'Eye',
  review: 'CheckCircle2',
  emergency: 'AlertTriangle'
}
</script>

<template>
  <div class="space-y-3">
    <h3 class="text-item-title flex items-center gap-2">
      <SafeIcon name="Zap" :size="18" class="text-accent" />
      常用模板
    </h3>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div
        v-for="template in templates"
        :key="template.id"
        :class="cn(
          'surface-base card-padding cursor-pointer transition-all duration-200 group',
          selectedTemplateId === template.id && 'ring-2 ring-primary border-primary'
        )"
        @click="emit('select', template.id)"
      >
        <div class="flex items-start justify-between mb-2">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center group-hover:bg-primary/30 transition-colors">
              <SafeIcon 
                :name="categoryIcons[template.category] || 'CheckCircle2'" 
                :size="16" 
                class="text-primary"
              />
            </div>
            <div>
              <h4 class="text-sm font-medium text-foreground">{{ template.name }}</h4>
              <p class="text-[10px] text-muted-foreground">{{ categoryLabels[template.category] }}</p>
            </div>
          </div>
          <div v-if="selectedTemplateId === template.id" class="w-5 h-5 rounded-full bg-primary flex items-center justify-center">
            <SafeIcon name="Check" :size="12" class="text-primary-foreground" />
          </div>
        </div>

        <p class="text-xs text-muted-foreground leading-relaxed mb-3">
          {{ template.description }}
        </p>

        <div class="flex items-center justify-between text-[10px]">
          <span class="px-2 py-1 rounded-full bg-muted/40 text-muted-foreground capitalize">
            {{ template.defaultPriority === 'high' ? '高优先级' : template.defaultPriority === 'medium' ? '中优先级' : '低优先级' }}
          </span>
          <Button 
            variant="ghost" 
            size="sm" 
            class="h-6 px-2 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
            @click.stop="emit('select', template.id)"
          >
            使用此模板
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

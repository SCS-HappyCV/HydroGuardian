
<script setup lang="ts">
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

const handleViewMap = () => {
  window.location.href = './risk-workspace.html'
}
</script>

<template>
  <div class="surface-base card-padding flex flex-col h-full">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-section-title">区域风险热力图</h3>
      <Button 
        variant="ghost" 
        size="icon" 
        class="h-6 w-6 text-muted-foreground hover:text-primary"
        @click="handleViewMap"
      >
        <SafeIcon name="Maximize2" :size="14" />
      </Button>
    </div>

    <div class="flex-1 flex items-center justify-center bg-muted/20 rounded-lg border border-border/30 min-h-[300px] relative overflow-hidden">
      <div class="absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-accent/10" />
      
      <div class="relative z-10 flex flex-col items-center justify-center text-center gap-4 p-4">
        <div class="w-16 h-16 rounded-full bg-gradient-to-br from-primary/30 to-accent/30 flex items-center justify-center shadow-lg shadow-primary/20">
          <SafeIcon name="MapPin" :size="32" class="text-primary" />
        </div>
        
        <div class="space-y-2">
          <p class="text-sm font-medium text-foreground">风险热力图预览</p>
          <p class="text-xs text-muted-foreground leading-relaxed">
            展示各区域风险分布情况<br/>点击查看完整地图分析
          </p>
        </div>

        <Button 
          variant="outline" 
          size="sm"
          class="mt-2 border-primary/20 hover:bg-primary/10 text-primary"
          @click="handleViewMap"
        >
          <SafeIcon name="Map" :size="14" class="mr-1.5" />
          进入风险分析区
        </Button>
      </div>
    </div>

    <div class="mt-4 grid grid-cols-2 gap-2 text-[10px]">
      <div class="flex items-center gap-1.5">
        <div class="w-2 h-2 rounded-full bg-destructive" />
        <span class="text-muted-foreground">高风险</span>
      </div>
      <div class="flex items-center gap-1.5">
        <div class="w-2 h-2 rounded-full" style="background-color: hsl(var(--warning))" />
        <span class="text-muted-foreground">中风险</span>
      </div>
      <div class="flex items-center gap-1.5">
        <div class="w-2 h-2 rounded-full" style="background-color: hsl(var(--success))" />
        <span class="text-muted-foreground">低风险</span>
      </div>
      <div class="flex items-center gap-1.5">
        <div class="w-2 h-2 rounded-full bg-accent" />
        <span class="text-muted-foreground">待复核</span>
      </div>
    </div>
  </div>
</template>

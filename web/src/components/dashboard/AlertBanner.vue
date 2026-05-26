
<script setup lang="ts">
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

const handleViewHealth = () => {
  window.location.href = './system-health.html'
}
</script>

<template>
  <Alert class="border-destructive/50 bg-destructive/10 text-destructive">
    <SafeIcon name="AlertTriangle" :size="16" class="h-4 w-4" />
    <AlertTitle>系统告警</AlertTitle>
    <AlertDescription class="flex items-center justify-between mt-2">
      <span>后端服务连接异常，部分功能可能受影响。</span>
      <Button 
        variant="ghost" 
        size="sm"
        class="text-destructive hover:bg-destructive/20"
        @click="handleViewHealth"
      >
        查看详情
        <SafeIcon name="ChevronRight" :size="14" class="ml-1" />
      </Button>
    </AlertDescription>
  </Alert>
</template>


<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { TaskLogData } from '@/data/TaskLogData'
import { ScrollArea } from '@/components/ui/scroll-area'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  logs: TaskLogData[]
}>()

const scrollContainer = ref<HTMLDivElement | null>(null)
const autoScroll = ref(true)

const sortedLogs = computed(() => {
  return [...props.logs].sort((a, b) => 
    new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
  )
})

const scrollToBottom = async () => {
  await nextTick()
  if (scrollContainer.value && autoScroll.value) {
    scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
  }
}

watch(() => props.logs.length, () => {
  scrollToBottom()
})

const formatTime = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const getLevelIcon = (level: string) => {
  const map = {
    info: 'Info',
    warn: 'AlertCircle',
    error: 'AlertTriangle'
  }
  return map[level as keyof typeof map] || 'MessageCircle'
}

const getLevelClass = (level: string) => {
  const map = {
    info: 'log-entry-info',
    warn: 'log-entry-warning',
    error: 'log-entry-error'
  }
  return map[level as keyof typeof map] || 'log-entry-info'
}
</script>

<template>
  <div class="surface-base flex flex-col h-[400px]">
    <div class="flex items-center justify-between card-padding border-b border-border/50">
      <h3 class="text-sm font-semibold">执行日志流</h3>
      <div class="flex items-center gap-2">
        <label class="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer hover:text-foreground transition-colors">
          <input 
            v-model="autoScroll" 
            type="checkbox" 
            class="w-3 h-3 rounded border-border cursor-pointer"
          />
          <span>自动滚动</span>
        </label>
      </div>
    </div>

    <ScrollArea class="flex-1 overflow-hidden">
      <div 
        ref="scrollContainer"
        class="scrollable-content p-4 space-y-2 font-mono text-xs"
      >
        <div 
          v-if="sortedLogs.length === 0"
          class="flex items-center justify-center h-full text-muted-foreground py-8"
        >
          <div class="text-center space-y-2">
            <SafeIcon name="FileText" :size="32" class="mx-auto opacity-20" />
            <p>暂无执行日志</p>
          </div>
        </div>

        <div 
          v-for="(log, index) in sortedLogs" 
          :key="log.id"
          :class="cn('log-entry', getLevelClass(log.level))"
        >
          <div class="flex items-start gap-2">
            <span class="text-muted-foreground shrink-0 w-20">
              [{{ formatTime(log.createdAt) }}]
            </span>
            <SafeIcon 
              :name="getLevelIcon(log.level)" 
              :size="12" 
              class="mt-0.5 shrink-0"
            />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-0.5">
                <span class="font-semibold uppercase text-[10px] tracking-wider">
                  {{ log.stepName }}
                </span>
                <span class="text-muted-foreground/60">{{ log.level.toUpperCase() }}</span>
              </div>
              <p class="break-words whitespace-pre-wrap">{{ log.message }}</p>
            </div>
          </div>
        </div>

        <div v-if="sortedLogs.length > 0" class="h-2" />
      </div>
    </ScrollArea>
  </div>
</template>

<style scoped>
.log-entry {
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

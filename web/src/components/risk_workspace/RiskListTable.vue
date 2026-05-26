
<script setup lang="ts">
import type { RiskEventData } from '@/data/RiskEventData'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import StatusBadge from '@/components/common/StatusBadge.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { cn } from '@/lib/utils'

interface Props {
  risks: RiskEventData[]
  selectedRiskId: string | null
}

const emit = defineEmits<{
  (e: 'row-click', risk: RiskEventData): void
}>()

const handleRowClick = (risk: RiskEventData) => {
  emit('row-click', risk)
}

const getLevelColor = (level?: string) => {
  switch (level) {
    case 'high':
      return 'text-destructive'
    case 'medium':
      return 'text-[hsl(var(--warning))]'
    case 'low':
      return 'text-[hsl(var(--success))]'
    case 'review_required':
      return 'text-accent'
    default:
      return 'text-foreground'
  }
}
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden">
    <div class="overflow-x-auto flex-1 min-h-0">
      <Table>
        <TableHeader class="sticky top-0 z-10 bg-card/95 backdrop-blur-sm">
          <TableRow class="border-b border-border/50 hover:bg-transparent">
            <TableHead class="w-24 h-10 px-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap">
              等级
            </TableHead>
            <TableHead class="flex-1 min-w-0 h-10 px-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap">
              风险标题
            </TableHead>
            <TableHead class="w-16 h-10 px-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap text-right">
              分数
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="risk in (risks || [])"
            :key="risk?.id || Math.random()"
            :class="cn(
              'border-b border-border/30 last:border-0 cursor-pointer transition-colors',
              selectedRiskId === risk?.id
                ? 'bg-primary/10 hover:bg-primary/15'
                : 'hover:bg-muted/40'
            )"
            @click="handleRowClick(risk)"
          >
            <TableCell class="w-24 px-3 py-2">
              <StatusBadge :status="risk?.level" size="sm" />
            </TableCell>
            <TableCell class="flex-1 min-w-0 px-3 py-2">
              <div class="truncate text-xs text-foreground font-medium">
                {{ risk?.title }}
              </div>
              <div class="truncate text-[10px] text-muted-foreground mt-0.5">
                {{ risk?.description }}
              </div>
            </TableCell>
            <TableCell class="w-16 px-3 py-2 text-right">
              <span :class="cn('text-xs font-bold', getLevelColor(risk?.level))">
                {{ risk?.score }}
              </span>
            </TableCell>
          </TableRow>

          <TableRow v-if="!risks || risks.length === 0">
            <TableCell colspan="3" class="h-24 text-center">
              <div class="flex flex-col items-center justify-center text-muted-foreground">
                <SafeIcon name="Inbox" :size="24" class="mb-1 opacity-30" />
                <span class="text-xs">暂无风险数据</span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>

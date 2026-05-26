
<script setup lang="ts">
import { ref, computed } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import SafeIcon from '@/components/common/SafeIcon.vue'
import SearchBar from '@/components/common/SearchBar.vue'
import { RuleService } from '@/data/RuleService'
import type { RuleData } from '@/data/RuleData'
import { cn } from '@/lib/utils'

const emit = defineEmits<{
  (e: 'edit', ruleId: string): void
  (e: 'refresh'): void
}>()

const rules = ref(RuleService.getAll())
const keyword = ref('')
const filterCategory = ref('all')
const filterActive = ref('all')

const filteredRules = computed(() => {
  return RuleService.query({
    keyword: keyword.value,
    filter: {
      category: filterCategory.value === 'all' ? undefined : (filterCategory.value as any),
      isActive: filterActive.value === 'all' ? undefined : filterActive.value === 'true'
    }
  })
})

const categoryMap: Record<string, string> = {
  hydrology: '水文监测',
  structure: '结构安全',
  operation: '运维管理'
}

const handleEdit = (ruleId: string) => {
  emit('edit', ruleId)
}

const handleResetFilters = () => {
  keyword.value = ''
  filterCategory.value = 'all'
  filterActive.value = 'all'
}
</script>

<template>
  <div class="flex flex-col gap-4 h-full min-h-0">
    <!-- Filter Bar -->
    <div class="flex flex-wrap items-center gap-3 p-4 surface-base">
      <SearchBar 
        v-model="keyword" 
        placeholder="搜索规则名称或条件..."
        class="flex-1 min-w-[200px]"
      />
      
      <Select v-model="filterCategory">
        <SelectTrigger class="w-[140px] h-9 bg-card/50">
          <SelectValue placeholder="选择分类" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部分类</SelectItem>
          <SelectItem value="hydrology">水文监测</SelectItem>
          <SelectItem value="structure">结构安全</SelectItem>
          <SelectItem value="operation">运维管理</SelectItem>
        </SelectContent>
      </Select>

      <Select v-model="filterActive">
        <SelectTrigger class="w-[140px] h-9 bg-card/50">
          <SelectValue placeholder="选择状态" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部状态</SelectItem>
          <SelectItem value="true">已启用</SelectItem>
          <SelectItem value="false">已禁用</SelectItem>
        </SelectContent>
      </Select>

      <Button 
        variant="ghost" 
        size="sm" 
        class="h-9 px-3 text-muted-foreground hover:text-foreground"
        @click="handleResetFilters"
      >
        <SafeIcon name="RotateCcw" :size="14" class="mr-2" />
        重置
      </Button>
    </div>

    <!-- Rules Table -->
    <div class="flex-1 min-h-0 overflow-hidden flex flex-col">
      <div class="overflow-x-auto flex-1">
        <Table>
          <TableHeader>
            <TableRow class="hover:bg-transparent border-b border-border">
              <TableHead class="w-32 whitespace-nowrap px-4 text-xs font-semibold uppercase">规则ID</TableHead>
              <TableHead class="w-48 whitespace-nowrap px-4 text-xs font-semibold uppercase">规则名称</TableHead>
              <TableHead class="w-24 whitespace-nowrap px-4 text-xs font-semibold uppercase">分类</TableHead>
              <TableHead class="w-32 whitespace-nowrap px-4 text-xs font-semibold uppercase">版本</TableHead>
              <TableHead class="flex-1 min-w-[200px] whitespace-nowrap px-4 text-xs font-semibold uppercase">触发条件</TableHead>
              <TableHead class="w-20 whitespace-nowrap px-4 text-xs font-semibold uppercase">状态</TableHead>
              <TableHead class="w-20 whitespace-nowrap px-4 text-xs font-semibold uppercase">调用次数</TableHead>
              <TableHead class="w-24 whitespace-nowrap px-4 text-xs font-semibold uppercase">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow 
              v-for="rule in filteredRules" 
              :key="rule.id"
              class="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors"
            >
              <TableCell class="px-4 py-3 text-xs font-mono text-muted-foreground">
                {{ rule.id }}
              </TableCell>
              <TableCell class="px-4 py-3 text-sm font-medium text-foreground">
                {{ rule.name }}
              </TableCell>
              <TableCell class="px-4 py-3">
                <Badge variant="outline" class="text-xs">
                  {{ categoryMap[rule.category] || rule.category }}
                </Badge>
              </TableCell>
              <TableCell class="px-4 py-3 text-sm text-muted-foreground">
                {{ rule.version }}
              </TableCell>
              <TableCell class="px-4 py-3 text-xs text-muted-foreground truncate max-w-xs">
                {{ rule.conditionSummary }}
              </TableCell>
              <TableCell class="px-4 py-3">
                <Badge 
                  :class="cn(
                    'text-xs',
                    rule.isActive 
                      ? 'bg-[hsl(var(--success))]/20 text-[hsl(var(--success))] border-[hsl(var(--success))]/30' 
                      : 'bg-muted/40 text-muted-foreground border-muted/50'
                  )"
                  variant="outline"
                >
                  {{ rule.isActive ? '启用' : '禁用' }}
                </Badge>
              </TableCell>
              <TableCell class="px-4 py-3 text-sm text-foreground font-medium">
                {{ rule.hitCount }}
              </TableCell>
              <TableCell class="px-4 py-3">
                <div class="flex items-center gap-1">
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    class="h-8 w-8 text-muted-foreground hover:text-primary"
                    @click="handleEdit(rule.id)"
                    title="编辑规则"
                  >
                    <SafeIcon name="Edit2" :size="14" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>

            <TableRow v-if="filteredRules.length === 0">
              <TableCell :colspan="8" class="h-32 text-center">
                <div class="flex flex-col items-center justify-center text-muted-foreground">
                  <SafeIcon name="Inbox" :size="32" class="mb-2 opacity-20" />
                  <span class="text-sm">暂无匹配的规则</span>
                </div>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </div>
  </div>
</template>

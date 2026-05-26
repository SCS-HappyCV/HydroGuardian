
<script setup lang="ts">
import { ref, computed } from 'vue'
import { Button } from '@/components/ui/button'
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
import { TemplateService } from '@/data/TemplateService'
import type { TemplateData } from '@/data/TemplateData'
import { cn } from '@/lib/utils'

const emit = defineEmits<{
  (e: 'edit', templateId: string): void
  (e: 'refresh'): void
}>()

const templates = ref(TemplateService.getAll())
const keyword = ref('')
const filterType = ref('all')
const filterEnabled = ref('all')

const filteredTemplates = computed(() => {
  return TemplateService.query({
    keyword: keyword.value,
    filter: {
      type: filterType.value === 'all' ? undefined : (filterType.value as any),
      isEnabled: filterEnabled.value === 'all' ? undefined : filterEnabled.value === 'true'
    }
  })
})

const typeMap: Record<string, string> = {
  dispatch: '处置建议',
  review: '复核建议'
}

const handleEdit = (templateId: string) => {
  emit('edit', templateId)
}

const handleResetFilters = () => {
  keyword.value = ''
  filterType.value = 'all'
  filterEnabled.value = 'all'
}
</script>

<template>
  <div class="flex flex-col gap-4 h-full min-h-0">
    <!-- Filter Bar -->
    <div class="flex flex-wrap items-center gap-3 p-4 surface-base">
      <SearchBar 
        v-model="keyword" 
        placeholder="搜索模板名称或内容..."
        class="flex-1 min-w-[200px]"
      />
      
      <Select v-model="filterType">
        <SelectTrigger class="w-[140px] h-9 bg-card/50">
          <SelectValue placeholder="选择类型" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部类型</SelectItem>
          <SelectItem value="dispatch">处置建议</SelectItem>
          <SelectItem value="review">复核建议</SelectItem>
        </SelectContent>
      </Select>

      <Select v-model="filterEnabled">
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

    <!-- Templates Table -->
    <div class="flex-1 min-h-0 overflow-hidden flex flex-col">
      <div class="overflow-x-auto flex-1">
        <Table>
          <TableHeader>
            <TableRow class="hover:bg-transparent border-b border-border">
              <TableHead class="w-32 whitespace-nowrap px-4 text-xs font-semibold uppercase">模板ID</TableHead>
              <TableHead class="w-40 whitespace-nowrap px-4 text-xs font-semibold uppercase">模板名称</TableHead>
              <TableHead class="w-24 whitespace-nowrap px-4 text-xs font-semibold uppercase">类型</TableHead>
              <TableHead class="w-40 whitespace-nowrap px-4 text-xs font-semibold uppercase">适用风险等级</TableHead>
              <TableHead class="flex-1 min-w-[200px] whitespace-nowrap px-4 text-xs font-semibold uppercase">模板内容</TableHead>
              <TableHead class="w-20 whitespace-nowrap px-4 text-xs font-semibold uppercase">状态</TableHead>
              <TableHead class="w-20 whitespace-nowrap px-4 text-xs font-semibold uppercase">调用次数</TableHead>
              <TableHead class="w-24 whitespace-nowrap px-4 text-xs font-semibold uppercase">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow 
              v-for="template in filteredTemplates" 
              :key="template.id"
              class="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors"
            >
              <TableCell class="px-4 py-3 text-xs font-mono text-muted-foreground">
                {{ template.id }}
              </TableCell>
              <TableCell class="px-4 py-3 text-sm font-medium text-foreground">
                {{ template.name }}
              </TableCell>
              <TableCell class="px-4 py-3">
                <Badge variant="outline" class="text-xs">
                  {{ typeMap[template.type] || template.type }}
                </Badge>
              </TableCell>
              <TableCell class="px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  <Badge 
                    v-for="level in template.applicableRiskLevels" 
                    :key="level"
                    variant="outline"
                    class="text-[10px]"
                    :class="cn(
                      level === 'high' && 'bg-destructive/20 text-destructive border-destructive/30',
                      level === 'medium' && 'bg-[hsl(var(--warning))]/20 text-[hsl(var(--warning))] border-[hsl(var(--warning))]/30',
                      level === 'low' && 'bg-[hsl(var(--success))]/20 text-[hsl(var(--success))] border-[hsl(var(--success))]/30',
                      level === 'review_required' && 'bg-accent/20 text-accent border-accent/30'
                    )"
                  >
                    {{ level === 'high' ? '高' : level === 'medium' ? '中' : level === 'low' ? '低' : '复核' }}
                  </Badge>
                </div>
              </TableCell>
              <TableCell class="px-4 py-3 text-xs text-muted-foreground truncate max-w-xs">
                {{ template.content }}
              </TableCell>
              <TableCell class="px-4 py-3">
                <Badge 
                  :class="cn(
                    'text-xs',
                    template.isEnabled 
                      ? 'bg-[hsl(var(--success))]/20 text-[hsl(var(--success))] border-[hsl(var(--success))]/30' 
                      : 'bg-muted/40 text-muted-foreground border-muted/50'
                  )"
                  variant="outline"
                >
                  {{ template.isEnabled ? '启用' : '禁用' }}
                </Badge>
              </TableCell>
              <TableCell class="px-4 py-3 text-sm text-foreground font-medium">
                {{ template.callCount }}
              </TableCell>
              <TableCell class="px-4 py-3">
                <div class="flex items-center gap-1">
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    class="h-8 w-8 text-muted-foreground hover:text-primary"
                    @click="handleEdit(template.id)"
                    title="编辑模板"
                  >
                    <SafeIcon name="Edit2" :size="14" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>

            <TableRow v-if="filteredTemplates.length === 0">
              <TableCell :colspan="8" class="h-32 text-center">
                <div class="flex flex-col items-center justify-center text-muted-foreground">
                  <SafeIcon name="Inbox" :size="32" class="mb-2 opacity-20" />
                  <span class="text-sm">暂无匹配的模板</span>
                </div>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </div>
  </div>
</template>

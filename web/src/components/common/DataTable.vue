
<script setup lang="ts">
import { ref, computed } from 'vue';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import SafeIcon from '@/components/common/SafeIcon.vue';

interface Column {
  key: string;
  label: string;
  sortable?: boolean;
  width?: string;
}

interface Props {
  columns: Column[];
  data: any[];
  rowKey: string;
  onRowClick?: (row: any) => void;
}

const props = defineProps<Props>();

// Sorting state
const sortKey = ref<string | null>(null);
const sortOrder = ref<'asc' | 'desc'>('asc');

const handleSort = (key: string) => {
  const column = props.columns.find(col => col.key === key);
  if (!column?.sortable) return;

  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortOrder.value = 'asc';
  }
};

const sortedData = computed(() => {
  if (!sortKey.value) return props.data;

  const order = sortOrder.value === 'asc' ? 1 : -1;
  return [...props.data].sort((a, b) => {
    const valA = a[sortKey.value!];
    const valB = b[sortKey.value!];

    if (valA < valB) return -1 * order;
    if (valA > valB) return 1 * order;
    return 0;
  });
});

const handleRowClick = (row: any) => {
  if (props.onRowClick) {
    props.onRowClick(row);
  }
};
</script>

<template>
  <div class="w-full flex flex-col min-h-0 bg-card rounded-[--radius] border border-border mt-4">
    <div class="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent border-b border-border">
            <TableHead
              v-for="col in columns"
              :key="col.key"
              :class="cn(
                'whitespace-nowrap h-12 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider',
                col.sortable && 'cursor-pointer select-none hover:text-foreground transition-colors',
                col.width || 'w-auto'
              )"
              @click="handleSort(col.key)"
            >
              <div class="flex items-center gap-2">
                {{ col.label }}
                <div v-if="col.sortable" class="flex flex-col">
                  <SafeIcon
                    v-if="sortKey === col.key && sortOrder === 'asc'"
                    name="ChevronUp"
                    :size="14"
                    class="text-primary"
                  />
                  <SafeIcon
                    v-else-if="sortKey === col.key && sortOrder === 'desc'"
                    name="ChevronDown"
                    :size="14"
                    class="text-primary"
                  />
                  <SafeIcon
                    v-else
                    name="ChevronsUpDown"
                    :size="14"
                    class="text-muted-foreground/30"
                  />
                </div>
              </div>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="row in sortedData"
            :key="row[rowKey]"
            :class="cn(
              'border-b border-border/50 last:border-0 transition-colors',
              onRowClick ? 'cursor-pointer hover:bg-muted/40' : 'hover:bg-muted/20'
            )"
            @click="handleRowClick(row)"
          >
            <TableCell
              v-for="col in columns"
              :key="col.key"
              class="px-4 py-3 text-sm text-card-foreground align-middle"
            >
              <slot :name="`cell-${col.key}`" :row="row">
                <span class="truncate block max-w-xs">
                  {{ row[col.key] ?? '-' }}
                </span>
              </slot>
            </TableCell>
          </TableRow>
          
          <TableRow v-if="sortedData.length === 0">
            <TableCell :colspan="columns.length" class="h-32 text-center">
              <div class="flex flex-col items-center justify-center text-muted-foreground">
                <SafeIcon name="Inbox" :size="32" class="mb-2 opacity-20" />
                <span class="text-sm">暂无数据</span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>

<style scoped>
/* 确保表格头部在纵向滚动时保持粘性（如果父级容器设置了高度） */
thead {
  @apply sticky top-0 z-10 bg-card/95 backdrop-blur-sm;
}
</style>

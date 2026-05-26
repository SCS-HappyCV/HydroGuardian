
<script setup lang="ts">
import { computed } from 'vue';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import SafeIcon from '@/components/common/SafeIcon.vue';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

const props = defineProps<PaginationProps>();

const visiblePages = computed(() => {
  const current = props.currentPage || 1;
  const total = props.totalPages || 1;
  const pages: (number | string)[] = [];

  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i);
  } else {
    pages.push(1);
    if (current > 4) pages.push('...');

    const start = Math.max(2, current - 1);
    const end = Math.min(total - 1, current + 1);

    for (let i = start; i <= end; i++) {
      pages.push(i);
    }

    if (current < total - 3) pages.push('...');
    pages.push(total);
  }
  return pages;
});

const handlePageClick = (page: number | string) => {
  if (typeof page === 'number' && page !== props.currentPage) {
    props.onPageChange(page);
  }
};

const handlePageSizeChange = (value: string) => {
  props.onPageSizeChange(parseInt(value, 10));
};

const startItem = computed(() => ((props.currentPage - 1) * props.pageSize) + 1);
const endItem = computed(() => Math.min(props.currentPage * props.pageSize, props.totalItems));
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-4 py-4">
    <!-- Left: Status & Page Size -->
    <div class="flex items-center gap-4 text-sm text-muted-foreground whitespace-nowrap shrink-0">
      <span>
        显示 {{ startItem }} - {{ endItem }} 条，共 {{ totalItems }} 条
      </span>
      <div class="flex items-center gap-2">
        <span>每页显示</span>
        <Select :model-value="props.pageSize.toString()" @update:model-value="handlePageSizeChange">
          <SelectTrigger class="h-8 w-[80px] bg-card/60">
            <SelectValue :placeholder="props.pageSize.toString()" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="10">10</SelectItem>
            <SelectItem value="20">20</SelectItem>
            <SelectItem value="50">50</SelectItem>
            <SelectItem value="100">100</SelectItem>
          </SelectContent>
        </Select>
        <span>条</span>
      </div>
    </div>

    <!-- Right: Pagination Controls -->
    <nav class="flex-1 min-w-0 flex justify-end">
      <div class="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          class="h-8 w-8 bg-card/60"
          :disabled="props.currentPage <= 1"
          @click="handlePageClick(props.currentPage - 1)"
        >
          <SafeIcon name="ChevronLeft" :size="16" />
        </Button>

        <template v-for="(page, index) in visiblePages" :key="index">
          <template v-if="page === '...'">
            <span class="px-2 text-muted-foreground">...</span>
          </template>
          <Button
            v-else
            variant="outline"
            size="sm"
            class="h-8 w-8 p-0 transition-all"
            :class="[
              props.currentPage === page
                ? 'bg-primary text-primary-foreground hover:bg-primary-hover border-primary'
                : 'bg-card/60 hover:bg-muted-hover border-border'
            ]"
            @click="handlePageClick(page)"
          >
            {{ page }}
          </Button>
        </template>

        <Button
          variant="outline"
          size="icon"
          class="h-8 w-8 bg-card/60"
          :disabled="props.currentPage >= props.totalPages"
          @click="handlePageClick(props.currentPage + 1)"
        >
          <SafeIcon name="ChevronRight" :size="16" />
        </Button>
      </div>
    </nav>
  </div>
</template>

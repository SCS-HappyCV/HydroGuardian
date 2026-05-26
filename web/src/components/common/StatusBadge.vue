
<script setup lang="ts">
import { computed } from 'vue';
import { Badge } from '@/components/ui/badge';
import SafeIcon from '@/components/common/SafeIcon.vue';
import { cn } from '@/lib/utils';

interface Props {
  status:
    | 'queued'
    | 'running'
    | 'success'
    | 'failed'
    | 'high'
    | 'medium'
    | 'low'
    | 'review_required'
    | 'todo'
    | 'doing'
    | 'review'
    | 'closed';
  size?: 'sm' | 'md' | 'lg';
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
});

const statusMap = {
  queued: {
    label: '排队中',
    icon: 'Clock',
    className: 'status-badge-queued',
  },
  running: {
    label: '执行中',
    icon: 'Loader2',
    className: 'status-badge-running',
    animate: true,
  },
  success: {
    label: '成功',
    icon: 'CheckCircle2',
    className: 'status-badge-success',
  },
  failed: {
    label: '失败',
    icon: 'XCircle',
    className: 'status-badge-failed',
  },
  high: {
    label: '高风险',
    icon: 'AlertTriangle',
    className: 'status-badge-high',
  },
  medium: {
    label: '中风险',
    icon: 'AlertCircle',
    className: 'status-badge-medium',
  },
  low: {
    label: '低风险',
    icon: 'Info',
    className: 'status-badge-low',
  },
  review_required: {
    label: '待复核',
    icon: 'ClipboardCheck',
    className: 'status-badge-review-required',
  },
  todo: {
    label: '待处理',
    icon: 'ListTodo',
    className: 'status-badge-todo',
  },
  doing: {
    label: '处理中',
    icon: 'UserCog',
    className: 'status-badge-doing',
  },
  review: {
    label: '复核中',
    icon: 'SearchCheck',
    className: 'status-badge-review',
  },
  closed: {
    label: '已关闭',
    icon: 'Archive',
    className: 'status-badge-closed',
  },
};

const config = computed(() => statusMap[props.status] || {
  label: props.status || 'Unknown',
  icon: 'HelpCircle',
  className: 'bg-muted text-muted-foreground',
});

const sizeClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'px-1.5 py-0 text-[10px] gap-1 h-5';
    case 'lg':
      return 'px-3 py-1 text-sm gap-2 h-8';
    default:
      return 'px-2 py-0.5 text-xs gap-1.5 h-6';
  }
});

const iconSize = computed(() => {
  switch (props.size) {
    case 'sm':
      return 10;
    case 'lg':
      return 16;
    default:
      return 12;
  }
});
</script>

<template>
  <Badge
    variant="outline"
    :class="
      cn(
        'inline-flex items-center font-medium border whitespace-nowrap transition-all',
        config.className,
        sizeClasses
      )
    "
  >
    <SafeIcon
      :name="config.icon"
      :size="iconSize"
      :class="cn('shrink-0', config.animate && 'animate-spin')"
    />
    <span>{{ config.label }}</span>
  </Badge>
</template>

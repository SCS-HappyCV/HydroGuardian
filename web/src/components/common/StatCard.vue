
<script setup lang="ts">
import { computed } from 'vue';
import SafeIcon from '@/components/common/SafeIcon.vue';
import { cn } from '@/lib/utils';

interface Trend {
  value: number;
  direction: 'up' | 'down';
}

interface Props {
  icon: string;
  label: string;
  value: string | number;
  trend?: Trend;
  color?: 'primary' | 'accent' | 'success' | 'warning' | 'destructive';
  href?: string;
}

const props = withDefaults(defineProps<Props>(), {
  color: 'primary',
});

const colorClasses = computed(() => {
  const mapping = {
    primary: 'text-primary bg-primary/10',
    accent: 'text-accent bg-accent/10',
    success: 'text-[hsl(var(--success))] bg-[hsl(var(--success))]/10',
    warning: 'text-[hsl(var(--warning))] bg-[hsl(var(--warning))]/10',
    destructive: 'text-destructive bg-destructive/10',
  };
  return mapping[props.color] || mapping.primary;
});

const trendClasses = computed(() => {
  if (!props.trend) return '';
  return props.trend.direction === 'up' 
    ? 'text-[hsl(var(--success))]' 
    : 'text-destructive';
});

const handleClick = () => {
  if (props.href) {
    window.location.href = props.href;
  }
};
</script>

<template>
  <div
    :class="cn(
      'stat-card w-full card-padding flex flex-col gap-3 group',
      href && 'cursor-pointer'
    )"
    @click="handleClick"
  >
    <div class="flex items-center justify-between">
      <div 
        :class="cn(
          'w-10 h-10 rounded-full flex items-center justify-center transition-transform group-hover:scale-110', 
          colorClasses
        )"
      >
        <SafeIcon :name="icon" :size="20" />
      </div>
      
      <div v-if="trend" :class="cn('flex items-center gap-0.5 text-xs font-medium', trendClasses)">
        <SafeIcon 
          :name="trend.direction === 'up' ? 'ArrowUpRight' : 'ArrowDownRight'" 
          :size="14" 
        />
        <span>{{ trend.value }}%</span>
      </div>
    </div>

    <div class="space-y-1">
      <p class="text-caption font-medium uppercase tracking-wider">
        {{ label }}
      </p>
      <h3 class="text-2xl font-bold tracking-tight text-foreground">
        {{ value }}
      </h3>
    </div>

    <!-- Interactive hover hint if href is present -->
    <div 
      v-if="href"
      class="mt-1 flex items-center text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
    >
      <span>查看详情</span>
      <SafeIcon name="ChevronRight" :size="10" class="ml-0.5" />
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
    
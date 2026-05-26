
<script setup lang="ts">
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import SafeIcon from '@/components/common/SafeIcon.vue';
import { toast } from 'vue-sonner';

interface FilterOption {
  value: string;
  label: string;
}

interface FilterField {
  key: string;
  label: string;
  options: FilterOption[];
}

const props = defineProps<{
  filters: FilterField[];
  modelValue: Record<string, string>;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, string>): void;
}>();

const handleUpdate = (key: string, value: string) => {
  const newValue = { ...props.modelValue, [key]: value };
  emit('update:modelValue', newValue);
};

const resetFilters = () => {
  const resetValue = props.filters.reduce((acc, filter) => {
    // Default to the first option if available (usually "All" sentinel)
    acc[filter.key] = filter.options[0]?.value || 'all';
    return acc;
  }, {} as Record<string, string>);
  
  emit('update:modelValue', resetValue);
  toast.success('筛选条件已重置');
};
</script>

<template>
  <div class="filter-bar">
    <div
      v-for="filter in filters"
      :key="filter.key"
      class="flex items-center gap-2"
    >
      <label :for="filter.key" class="text-label whitespace-nowrap">
        {{ filter.label }}
      </label>
      <Select
        :model-value="modelValue[filter.key] || 'all'"
        @update:model-value="(val) => handleUpdate(filter.key, val)"
      >
        <SelectTrigger :id="filter.key" class="w-[140px] h-9 bg-card/50">
          <SelectValue :placeholder="`选择${filter.label}`" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem
            v-for="option in filter.options"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <Button
      variant="ghost"
      size="sm"
      class="h-9 px-3 text-muted-foreground hover:text-foreground"
      @click="resetFilters"
    >
      <SafeIcon name="RotateCcw" :size="14" class="mr-2" />
      重置
    </Button>
  </div>
</template>

<style scoped>
/* Ensure the filter bar is always concise and fits standard layout */
.filter-bar {
  @apply flex flex-wrap items-center gap-4 py-2;
}
</style>

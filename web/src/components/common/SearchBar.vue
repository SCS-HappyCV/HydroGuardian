
<script setup lang="ts">
import { Input } from '@/components/ui/input';
import SafeIcon from '@/components/common/SafeIcon.vue';

interface SearchBarProps {
  placeholder?: string;
  modelValue: string;
}

const props = withDefaults(defineProps<SearchBarProps>(), {
  placeholder: '搜索...',
  modelValue: '',
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
}>();

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit('update:modelValue', target.value);
};
</script>

<template>
  <div class="relative w-full max-w-sm flex items-center">
    <div class="absolute left-3 flex items-center justify-center pointer-events-none text-muted-foreground">
      <SafeIcon 
        name="Search" 
        :size="16" 
        :stroke-width="2" 
      />
    </div>
    <Input
      type="text"
      :placeholder="placeholder"
      :value="modelValue"
      @input="handleInput"
      class="pl-9 bg-muted/40 border-border focus:bg-muted/60 transition-colors"
    />
  </div>
</template>

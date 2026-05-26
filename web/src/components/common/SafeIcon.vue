<script setup lang="ts">
import { computed } from 'vue';
import * as LucideIcons from 'lucide-vue-next';
import { Circle } from 'lucide-vue-next';

interface Props {
  name: string;
  size?: number | string;
  color?: string;
  strokeWidth?: number | string;
  class?: string;
}

const props = withDefaults(defineProps<Props>(), {
  size: 24,
  strokeWidth: 2,
});

const IconComponent = computed(() => {
  const icon = (LucideIcons as any)[props.name];
  if (!icon) {
    console.warn(`SafeIcon: icon "${props.name}" not found in lucide-vue-next, using fallback`);
    return Circle;
  }
  return icon;
});
</script>

<template>
  <component
    :is="IconComponent"
    :size="size"
    :color="color"
    :stroke-width="strokeWidth"
    :class="props.class"
  />
</template>

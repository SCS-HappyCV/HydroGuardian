
<script setup lang="ts">
import Breadcrumb from './Breadcrumb.vue';
import { Separator } from '@/components/ui/separator';

interface BreadcrumbItemData {
  label: string;
  href?: string;
}

const props = defineProps<{
  title: string;
  subtitle?: string;
  breadcrumb?: BreadcrumbItemData[];
}>();
</script>

<template>
  <header class="flex flex-col gap-4 px-6 pt-6 pb-4 bg-background/50 backdrop-blur-sm sticky top-0 z-10">
    <div class="flex flex-col gap-2">
      <Breadcrumb v-if="breadcrumb && breadcrumb.length > 0" :items="breadcrumb" />
      <div class="flex items-center justify-between gap-4">
        <div class="space-y-1">
          <h1 class="text-page-title text-2xl md:text-3xl">
            {{ title }}
          </h1>
          <p v-if="subtitle" class="text-body text-sm md:text-base">
            {{ subtitle }}
          </p>
        </div>
        
        <div class="flex items-center gap-2">
          <slot name="actions" />
        </div>
      </div>
    </div>
    <Separator class="opacity-50" />
  </header>
</template>

<style scoped>
header {
  border-bottom: 1px solid transparent;
}
</style>

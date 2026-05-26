
<script setup lang="ts">
import { computed } from 'vue';
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';

interface BreadcrumbItemData {
  label: string;
  href?: string;
}

const props = defineProps<{
  items: BreadcrumbItemData[];
}>();

const breadcrumbItems = computed(() => props.items ?? []);
</script>

<template>
  <Breadcrumb v-if="breadcrumbItems.length > 0">
    <BreadcrumbList>
      <template v-for="(item, index) in breadcrumbItems" :key="index">
        <BreadcrumbItem>
          <template v-if="item.href && index < breadcrumbItems.length - 1">
            <BreadcrumbLink :href="item.href" class="interactive">
              {{ item.label }}
            </BreadcrumbLink>
          </template>
          <template v-else>
            <BreadcrumbPage>{{ item.label }}</BreadcrumbPage>
          </template>
        </BreadcrumbItem>
        <BreadcrumbSeparator v-if="index < breadcrumbItems.length - 1" />
      </template>
    </BreadcrumbList>
  </Breadcrumb>
</template>

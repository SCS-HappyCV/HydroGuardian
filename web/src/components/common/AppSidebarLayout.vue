
<script setup lang="ts">
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import AppSidebar from './AppSidebar.vue'

const props = defineProps<{
  currentPath: string
}>()

const isClient = ref(true)

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true
  })
})
</script>

<template>
  <SidebarProvider v-if="isClient" class="h-full">
    <AppSidebar :currentPath="currentPath" />
    <SidebarInset class="flex flex-col min-h-0 bg-background overflow-hidden relative">
      <div class="absolute inset-0 glow-background pointer-events-none opacity-40" />
      <div class="flex-1 overflow-y-auto min-h-0 relative z-10">
        <slot />
      </div>
    </SidebarInset>
  </SidebarProvider>
  <div v-else class="h-full flex items-center justify-center bg-background">
    <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
  </div>
</template>

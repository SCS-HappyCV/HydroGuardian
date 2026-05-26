
<script setup lang="ts">
import { ref } from 'vue'
import type { RiskLayerData } from '@/data/RiskLayerData'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import SafeIcon from '@/components/common/SafeIcon.vue'

interface Props {
  layers: RiskLayerData[]
}

const props = defineProps<Props>()

const layerStates = ref<Record<string, boolean>>(
  props.layers.reduce((acc, layer) => {
    acc[layer.id] = layer.isEnabled
    return acc
  }, {} as Record<string, boolean>)
)

const toggleLayer = (layerId: string) => {
  layerStates.value[layerId] = !layerStates.value[layerId]
}
</script>

<template>
  <div class="surface-base card-padding">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-foreground flex items-center gap-2">
        <SafeIcon name="Layers" :size="16" />
        证据图层
      </h3>
      <Button variant="ghost" size="icon" class="h-6 w-6" title="图层设置">
        <SafeIcon name="Settings" :size="14" />
      </Button>
    </div>

    <div class="space-y-2">
      <div
        v-for="layer in layers"
        :key="layer.id"
        class="flex items-center gap-2 p-2 rounded hover:bg-muted/30 transition-colors cursor-pointer"
        @click="toggleLayer(layer.id)"
      >
        <Checkbox
          :checked="layerStates[layer.id]"
          class="h-4 w-4"
        />
        <SafeIcon
          :name="layer.iconName"
          :size="14"
          :class="layerStates[layer.id] ? 'text-primary' : 'text-muted-foreground/50'"
        />
        <span class="text-xs text-foreground flex-1">{{ layer.name }}</span>
      </div>
    </div>
  </div>
</template>

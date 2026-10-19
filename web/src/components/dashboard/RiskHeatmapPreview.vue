<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import RealSpatialMap, { type SpatialMapArea, type SpatialMapBounds, type SpatialMapMarker } from '@/components/common/RealSpatialMap.vue'
import type { RiskEventData } from '@/data/RiskEventData'

const props = withDefaults(defineProps<{ risks?: RiskEventData[] }>(), { risks: () => [] })
const spatialRisks = computed(() => props.risks.filter(risk => risk.location))
const markers = computed<SpatialMapMarker[]>(() => spatialRisks.value.map(risk => ({
  id: risk.id, title: risk.title, longitude: risk.location!.longitude, latitude: risk.location!.latitude, level: risk.level, subtitle: `风险分数 ${risk.score}`,
})))
const areas = computed<SpatialMapArea[]>(() => spatialRisks.value.filter(risk => risk.location?.geographicBBox).map(risk => ({
  id: risk.id, title: risk.title, bounds: risk.location!.geographicBBox!, level: risk.level,
})))
const bounds = computed<SpatialMapBounds | undefined>(() => {
  const values = spatialRisks.value.flatMap(risk => risk.location?.geographicBBox ? [risk.location.geographicBBox] : [])
  if (!values.length) return undefined
  return {
    west: Math.min(...values.map(item => item.west)), south: Math.min(...values.map(item => item.south)),
    east: Math.max(...values.map(item => item.east)), north: Math.max(...values.map(item => item.north)),
  }
})

function handleViewMap(id?: string) {
  window.location.href = `./risk-workspace.html${id ? `?riskId=${encodeURIComponent(id)}` : ''}`
}
</script>

<template>
  <div class="surface-base card-padding flex h-full flex-col">
    <div class="mb-4 flex items-start justify-between gap-3">
      <div><h3 class="text-section-title">区域风险实景分布</h3><p class="mt-1 text-[10px] text-muted-foreground">基于任务空间成果自动定位</p></div>
      <Button variant="ghost" size="icon" class="h-7 w-7 text-muted-foreground hover:text-primary" @click="handleViewMap()"><SafeIcon name="Maximize2" :size="14" /></Button>
    </div>

    <RealSpatialMap :bounds="bounds" :markers="markers" :areas="areas" height="300px" compact @select="handleViewMap" />

    <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-muted-foreground">
        <span class="flex items-center gap-1.5"><i class="h-2 w-2 rounded-full bg-rose-400" />高风险</span>
        <span class="flex items-center gap-1.5"><i class="h-2 w-2 rounded-full bg-amber-300" />中风险</span>
        <span class="flex items-center gap-1.5"><i class="h-2 w-2 rounded-full bg-emerald-400" />低风险</span>
        <span class="flex items-center gap-1.5"><i class="h-2 w-2 rounded-full bg-violet-400" />待复核</span>
      </div>
      <span class="text-[10px] font-medium text-cyan-300">{{ spatialRisks.length }} 个已定位目标</span>
    </div>
  </div>
</template>

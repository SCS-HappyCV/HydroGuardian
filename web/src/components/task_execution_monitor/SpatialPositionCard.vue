<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import RealSpatialMap, { type SpatialMapArea, type SpatialMapMarker } from '@/components/common/RealSpatialMap.vue'
import type { AgentEvidenceRegionView, AgentRiskView, AgentSpatialContextView } from '@/lib/agent-presentation-types'

const props = withDefaults(defineProps<{ spatial?: AgentSpatialContextView; regions?: AgentEvidenceRegionView[]; risks?: AgentRiskView[] }>(), {
  regions: () => [], risks: () => [],
})

const primary = computed(() => props.spatial?.primary)
const coverage = computed(() => {
  const bounds = primary.value?.projectedBounds
  if (!bounds) return undefined
  return { width: bounds.maxX - bounds.minX, height: bounds.maxY - bounds.minY }
})
const alignmentLabel = computed(() => {
  const value = props.spatial?.alignmentErrorMeters
  if (value === undefined) return '单源空间基准'
  if (value <= 0.01) return '多源厘米级吻合'
  if (value <= 1) return '多源空间对齐'
  return '建议复核配准误差'
})
const roleLabels: Record<string, string> = {
  before_image_path: '前时相影像', after_image_path: '后时相影像', image_path: '正射影像', point_cloud_path: '三维点云', scene: '场景基准',
}
const mapBounds = computed(() => primary.value?.geographicBounds)
const mapMarkers = computed<SpatialMapMarker[]>(() => {
  return props.regions.filter(item => item.geographicCenter).map(item => ({
    id: item.regionId, title: props.risks.find(risk => risk.regionId === item.regionId)?.title || item.label,
    longitude: item.geographicCenter!.longitude, latitude: item.geographicCenter!.latitude,
    level: props.risks.find(risk => risk.regionId === item.regionId)?.riskLevel || (item.status === 'review_required' ? 'review_required' : 'target'), subtitle: item.summary,
  }))
})
const mapAreas = computed<SpatialMapArea[]>(() => props.regions.filter(item => item.geographicBBox).map(item => ({
  id: item.regionId, title: item.label, bounds: item.geographicBBox!, level: item.status === 'review_required' ? 'review_required' : 'target',
})))

function coordinate(value?: number, digits = 6) {
  return value === undefined ? '—' : value.toFixed(digits)
}
</script>

<template>
  <section v-if="spatial && primary" class="relative overflow-hidden rounded-3xl border border-emerald-400/15 bg-[#07151a]/90 shadow-[0_24px_70px_rgba(0,0,0,0.24)]">
    <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_10%,rgba(16,185,129,0.12),transparent_32%),radial-gradient(circle_at_90%_15%,rgba(34,211,238,0.08),transparent_30%)]" />
    <div class="relative grid lg:grid-cols-[minmax(0,1fr)_minmax(420px,.78fr)]">
      <div class="p-5 sm:p-6">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="grid h-10 w-10 place-items-center rounded-xl border border-emerald-400/20 bg-emerald-400/10 text-emerald-300"><SafeIcon name="MapPinned" :size="20" /></span>
            <div><h2 class="text-base font-semibold text-white">空间定位基准已建立</h2><p class="mt-1 text-[11px] text-slate-400">影像像素、点云坐标与现场经纬度已建立转换关系</p></div>
          </div>
          <span class="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-[10px] text-emerald-200"><span class="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_8px_rgba(110,231,183,0.8)]" />{{ alignmentLabel }}</span>
        </div>

        <div class="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div class="rounded-2xl border border-white/[0.065] bg-black/15 p-4"><p class="text-[9px] tracking-[0.16em] text-slate-600">LONGITUDE</p><p class="mt-2 font-mono text-lg text-emerald-200">{{ coordinate(primary.center?.longitude) }}°</p><p class="mt-1 text-[10px] text-slate-500">场景中心经度</p></div>
          <div class="rounded-2xl border border-white/[0.065] bg-black/15 p-4"><p class="text-[9px] tracking-[0.16em] text-slate-600">LATITUDE</p><p class="mt-2 font-mono text-lg text-cyan-200">{{ coordinate(primary.center?.latitude) }}°</p><p class="mt-1 text-[10px] text-slate-500">场景中心纬度</p></div>
          <div class="rounded-2xl border border-white/[0.065] bg-black/15 p-4"><p class="text-[9px] tracking-[0.16em] text-slate-600">COORDINATE SYSTEM</p><p class="mt-2 font-mono text-lg text-slate-200">EPSG:{{ primary.epsg }}</p><p class="mt-1 truncate text-[10px] text-slate-500">{{ primary.crsName }}</p></div>
          <div class="rounded-2xl border border-white/[0.065] bg-black/15 p-4"><p class="text-[9px] tracking-[0.16em] text-slate-600">COVERAGE</p><p class="mt-2 font-mono text-lg text-slate-200">{{ coverage ? `${coverage.width.toFixed(0)} × ${coverage.height.toFixed(0)}` : '—' }}<small v-if="coverage" class="ml-1 text-[10px] text-slate-500">m</small></p><p class="mt-1 text-[10px] text-slate-500">真实空间覆盖范围</p></div>
        </div>

        <div class="mt-4 flex flex-wrap gap-2">
          <span v-for="asset in spatial.assets" :key="asset.role" class="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.07] bg-white/[0.035] px-2.5 py-1.5 text-[10px] text-slate-400"><SafeIcon :name="asset.sourceType === 'point_cloud' ? 'Box' : 'Image'" :size="12" :class="asset.normalized ? 'text-amber-300' : 'text-emerald-300'" />{{ roleLabels[asset.role] || asset.role }}<span class="text-slate-600">·</span>EPSG:{{ asset.epsg }}<span v-if="asset.normalized" class="text-amber-300/80">已校正</span></span>
        </div>
      </div>

      <div class="relative overflow-hidden border-t border-white/[0.06] bg-[#061015] p-3 lg:border-l lg:border-t-0">
        <RealSpatialMap :center="primary.center" :bounds="mapBounds" :markers="mapMarkers" :areas="mapAreas" height="340px" />
      </div>
    </div>
  </section>
</template>

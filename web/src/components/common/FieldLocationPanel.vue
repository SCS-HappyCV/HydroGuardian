<script setup lang="ts">
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import SafeIcon from '@/components/common/SafeIcon.vue'
import RealSpatialMap, { type SpatialMapArea, type SpatialMapMarker } from '@/components/common/RealSpatialMap.vue'
import { Button } from '@/components/ui/button'
import type { SpatialLocationData } from '@/lib/spatial-location'
import {
  bearingDegrees,
  directionLabel,
  distanceMeters,
  formatGeographicCoordinate,
  formatProjectedCoordinate,
  mapViewUrl,
  mobileNavigationUrl,
} from '@/lib/spatial-location'

const props = withDefaults(defineProps<{
  location?: SpatialLocationData
  title?: string
  label?: string
  compact?: boolean
}>(), {
  title: '现场目标位置',
  label: '风险核查点',
  compact: false,
})

const locating = ref(false)
const devicePosition = ref<{ longitude: number; latitude: number; accuracy: number } | null>(null)

const projected = computed(() => props.location ? formatProjectedCoordinate(props.location) : undefined)
const distance = computed(() => props.location && devicePosition.value
  ? distanceMeters(devicePosition.value, props.location)
  : undefined)
const direction = computed(() => props.location && devicePosition.value
  ? directionLabel(bearingDegrees(devicePosition.value, props.location))
  : undefined)
const distanceLabel = computed(() => {
  if (distance.value === undefined) return '等待现场定位'
  return distance.value < 1000 ? `${Math.round(distance.value)} m` : `${(distance.value / 1000).toFixed(2)} km`
})
const mapMarkers = computed<SpatialMapMarker[]>(() => {
  const result: SpatialMapMarker[] = []
  if (props.location) result.push({ id: 'target', title: props.label, longitude: props.location.longitude, latitude: props.location.latitude, level: 'target' })
  if (devicePosition.value) result.push({ id: 'device', title: '我的现场位置', longitude: devicePosition.value.longitude, latitude: devicePosition.value.latitude, level: 'device', subtitle: `定位精度 ±${Math.round(devicePosition.value.accuracy)} m` })
  return result
})
const mapAreas = computed<SpatialMapArea[]>(() => props.location?.geographicBBox ? [{ id: 'target-area', title: `${props.label}空间范围`, bounds: props.location.geographicBBox, level: 'target' }] : [])

async function copyCoordinate() {
  if (!props.location) return
  const text = formatGeographicCoordinate(props.location)
  try {
    await navigator.clipboard.writeText(text)
    toast.success('目标坐标已复制')
  } catch {
    toast.error('坐标复制失败，请手动记录')
  }
}

function openMap() {
  if (!props.location) return
  window.open(mapViewUrl(props.location), '_blank', 'noopener,noreferrer')
}

function startNavigation() {
  if (!props.location) return
  window.location.href = mobileNavigationUrl(props.location, props.label)
}

function locateDevice() {
  if (!navigator.geolocation) {
    toast.error('当前设备不支持位置服务')
    return
  }
  locating.value = true
  navigator.geolocation.getCurrentPosition(
    (position) => {
      devicePosition.value = {
        longitude: position.coords.longitude,
        latitude: position.coords.latitude,
        accuracy: position.coords.accuracy,
      }
      locating.value = false
      toast.success('现场位置已更新')
    },
    (error) => {
      locating.value = false
      toast.error(error.code === error.PERMISSION_DENIED ? '请授权位置权限后重试' : '暂时无法获取现场位置')
    },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 15000 },
  )
}
</script>

<template>
  <section class="overflow-hidden rounded-xl border border-cyan-400/20 bg-[linear-gradient(145deg,rgba(14,52,70,.72),rgba(7,21,34,.92))]">
    <div class="relative p-3">
      <div class="pointer-events-none absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(103,232,249,.18)_1px,transparent_1px),linear-gradient(90deg,rgba(103,232,249,.18)_1px,transparent_1px)] [background-size:24px_24px]" />
      <div class="relative flex items-start justify-between gap-3">
        <div class="flex min-w-0 items-center gap-2.5">
          <span class="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200 shadow-[0_0_22px_rgba(34,211,238,.14)]">
            <SafeIcon name="MapPinned" :size="17" />
          </span>
          <div class="min-w-0">
            <h3 class="text-xs font-semibold text-white">{{ title }}</h3>
            <p class="mt-0.5 text-[10px] text-slate-400">{{ location ? '空间证据坐标已锁定' : '当前风险未携带可导航坐标' }}</p>
          </div>
        </div>
        <span v-if="location" class="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2 py-1 text-[9px] font-semibold text-emerald-200">可导航</span>
      </div>

      <template v-if="location">
        <div class="relative mt-3" :class="compact ? 'space-y-3' : 'grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,.65fr)]'">
          <div>
            <RealSpatialMap
              :center="location"
              :bounds="location.geographicBBox"
              :markers="mapMarkers"
              :areas="mapAreas"
              :height="compact ? '210px' : '330px'"
              :compact="compact"
            />
          </div>

          <div class="flex min-w-0 flex-col rounded-xl border border-white/[0.07] bg-black/10 p-3">
            <div class="grid gap-2" :class="compact ? 'grid-cols-1' : 'sm:grid-cols-2 xl:grid-cols-1'">
              <div class="rounded-lg border border-white/10 bg-black/20 px-3 py-2.5">
                <div class="text-[9px] uppercase tracking-[0.16em] text-slate-500">CGCS2000 经纬度</div>
                <div class="mt-1 font-mono text-xs font-semibold text-cyan-100">{{ formatGeographicCoordinate(location) }}</div>
              </div>
              <div class="rounded-lg border border-white/10 bg-black/20 px-3 py-2.5">
                <div class="text-[9px] uppercase tracking-[0.16em] text-slate-500">现场距离</div>
                <div class="mt-1 flex items-center gap-2 text-xs font-semibold text-white">
                  <span>{{ distanceLabel }}</span>
                  <span v-if="direction" class="text-cyan-300">· {{ direction }}方向</span>
                </div>
              </div>
            </div>
            <div v-if="!compact" class="mt-3 space-y-1.5 rounded-lg border border-white/[0.06] bg-white/[0.025] px-3 py-2.5 text-[10px] text-slate-400">
              <div v-if="projected" class="flex items-center justify-between gap-3"><span>投影坐标</span><span class="truncate font-mono text-slate-300">{{ projected }}</span></div>
              <div class="flex items-center justify-between gap-3"><span>空间基准</span><span class="truncate text-right text-slate-300">{{ location.crsName || (location.epsg ? `EPSG:${location.epsg}` : 'CGCS2000') }}</span></div>
              <div v-if="devicePosition" class="flex items-center justify-between gap-3"><span>定位精度</span><span class="text-slate-300">±{{ Math.round(devicePosition.accuracy) }} m</span></div>
            </div>
            <div class="mt-auto grid grid-cols-2 gap-2 pt-3">
              <Button variant="outline" size="sm" class="h-8 gap-1.5 border-white/10 bg-white/[0.04] text-[11px]" @click="copyCoordinate"><SafeIcon name="Copy" :size="12" />复制坐标</Button>
              <Button variant="outline" size="sm" class="h-8 gap-1.5 border-white/10 bg-white/[0.04] text-[11px]" @click="openMap"><SafeIcon name="Map" :size="12" />地图查看</Button>
              <Button variant="outline" size="sm" class="h-8 gap-1.5 border-white/10 bg-white/[0.04] text-[11px]" :disabled="locating" @click="locateDevice"><SafeIcon :name="locating ? 'Loader2' : 'LocateFixed'" :size="12" :class="locating && 'animate-spin'" />{{ locating ? '定位中' : '现场定位' }}</Button>
              <Button size="sm" class="h-8 gap-1.5 bg-cyan-500 text-[11px] text-slate-950 hover:bg-cyan-400" @click="startNavigation"><SafeIcon name="Navigation" :size="12" />现场导航</Button>
            </div>
          </div>
        </div>
      </template>
      <div v-else class="relative mt-3 rounded-lg border border-dashed border-white/10 px-3 py-4 text-center text-[11px] text-slate-500">
        完成带坐标的影像或点云分析后自动生成目标位置
      </div>
    </div>
  </section>
</template>

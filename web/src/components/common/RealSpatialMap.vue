<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Map as LeafletMap, Layer, LatLngBoundsExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import SafeIcon from '@/components/common/SafeIcon.vue'

export interface SpatialMapBounds {
  west: number
  south: number
  east: number
  north: number
}

export interface SpatialMapMarker {
  id: string
  title: string
  longitude: number
  latitude: number
  level?: 'high' | 'medium' | 'low' | 'review_required' | 'target' | 'device'
  subtitle?: string
}

export interface SpatialMapArea {
  id: string
  title: string
  bounds: SpatialMapBounds
  level?: SpatialMapMarker['level']
}

const props = withDefaults(defineProps<{
  center?: { longitude: number; latitude: number }
  bounds?: SpatialMapBounds
  markers?: SpatialMapMarker[]
  areas?: SpatialMapArea[]
  selectedId?: string | null
  hoveredId?: string | null
  height?: string
  compact?: boolean
  interactive?: boolean
}>(), {
  markers: () => [],
  areas: () => [],
  selectedId: null,
  hoveredId: null,
  height: '360px',
  compact: false,
  interactive: true,
})

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'hover', id: string | null): void
}>()
const mapHost = ref<HTMLElement | null>(null)
const tileReady = ref(false)
const tileSlow = ref(false)
const mapReady = ref(false)
let map: LeafletMap | undefined
let dynamicLayers: Layer[] = []
let resizeObserver: ResizeObserver | undefined
let leaflet: typeof import('leaflet') | undefined
let tileStatusTimer: ReturnType<typeof setTimeout> | undefined

const validCenter = computed(() => {
  if (props.center && Number.isFinite(props.center.longitude) && Number.isFinite(props.center.latitude)) return props.center
  const first = props.markers.find(item => Number.isFinite(item.longitude) && Number.isFinite(item.latitude))
  if (first) return { longitude: first.longitude, latitude: first.latitude }
  if (props.bounds) return { longitude: (props.bounds.west + props.bounds.east) / 2, latitude: (props.bounds.south + props.bounds.north) / 2 }
  return undefined
})

const hasSpatialData = computed(() => Boolean(validCenter.value || props.bounds || props.markers.length || props.areas.length))
const tileStatusLabel = computed(() => tileReady.value
  ? '真实地图已定位'
  : tileSlow.value ? '空间位置已定位 · 底图加载中' : '正在加载地图图层')
const colors: Record<NonNullable<SpatialMapMarker['level']>, string> = {
  high: '#fb7185', medium: '#fbbf24', low: '#34d399', review_required: '#a78bfa', target: '#22d3ee', device: '#60a5fa',
}

function clearDynamicLayers() {
  if (!map) return
  dynamicLayers.forEach(layer => map?.removeLayer(layer))
  dynamicLayers = []
}

function asLeafletBounds(bounds: SpatialMapBounds): LatLngBoundsExpression {
  return [[bounds.south, bounds.west], [bounds.north, bounds.east]]
}

function drawSpatialData() {
  if (!map || !leaflet) return
  clearDynamicLayers()
  const L = leaflet

  if (props.bounds) {
    const layer = L.rectangle(asLeafletBounds(props.bounds), {
      color: '#22d3ee', weight: 1.5, dashArray: '7 6', fillColor: '#22d3ee', fillOpacity: 0.055,
    }).addTo(map).bindTooltip('任务场景覆盖范围', { direction: 'top' })
    dynamicLayers.push(layer)
  }

  props.areas.forEach(area => {
    const color = colors[area.level || 'target']
    const selected = props.selectedId === area.id
    const hovered = props.hoveredId === area.id
    const layer = L.rectangle(asLeafletBounds(area.bounds), {
      color, weight: selected ? 3 : hovered ? 2.5 : 2, fillColor: color, fillOpacity: selected ? 0.23 : hovered ? 0.17 : 0.1,
    }).addTo(map).bindTooltip(area.title, { direction: 'top' })
    layer.on('click', () => emit('select', area.id))
    layer.on('mouseover', () => emit('hover', area.id))
    layer.on('mouseout', () => emit('hover', null))
    dynamicLayers.push(layer)
  })

  props.markers.forEach(marker => {
    if (!Number.isFinite(marker.longitude) || !Number.isFinite(marker.latitude)) return
    const color = colors[marker.level || 'target']
    const selected = props.selectedId === marker.id
    const hovered = props.hoveredId === marker.id
    const size = selected ? 22 : hovered ? 19 : 16
    const icon = L.divIcon({
      className: 'hg-spatial-marker',
      html: `<span class="${selected ? 'is-selected' : hovered ? 'is-hovered' : ''}" style="--marker:${color};--size:${size}px"><i></i></span>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    })
    const layer = L.marker([marker.latitude, marker.longitude], { icon }).addTo(map)
      .bindTooltip(`<strong>${marker.title}</strong>${marker.subtitle ? `<br><span>${marker.subtitle}</span>` : ''}`, { direction: 'top' })
    layer.on('click', () => emit('select', marker.id))
    layer.on('mouseover', () => emit('hover', marker.id))
    layer.on('mouseout', () => emit('hover', null))
    dynamicLayers.push(layer)
  })

  if (props.bounds) map.fitBounds(asLeafletBounds(props.bounds), { padding: [28, 28], maxZoom: 18 })
  else if (props.areas.length) {
    const group = L.latLngBounds([])
    props.areas.forEach(item => group.extend(asLeafletBounds(item.bounds)))
    map.fitBounds(group, { padding: [28, 28], maxZoom: 18 })
  }
  else if (props.markers.length > 1) map.fitBounds(props.markers.map(item => [item.latitude, item.longitude]), { padding: [36, 36], maxZoom: 18 })
  else if (validCenter.value) map.setView([validCenter.value.latitude, validCenter.value.longitude], 17)
}

onMounted(async () => {
  if (!mapHost.value || !hasSpatialData.value) return
  leaflet = await import('leaflet')
  await nextTick()
  if (!mapHost.value) return
  map = leaflet.map(mapHost.value, {
    zoomControl: false,
    attributionControl: true,
    dragging: props.interactive,
    scrollWheelZoom: props.interactive,
    doubleClickZoom: props.interactive,
  })
  if (props.interactive) leaflet.control.zoom({ position: 'bottomright' }).addTo(map)
  tileStatusTimer = setTimeout(() => { tileSlow.value = true }, 3500)
  leaflet.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).on('load', () => {
    tileReady.value = true
    tileSlow.value = false
    if (tileStatusTimer) clearTimeout(tileStatusTimer)
  }).addTo(map)
  drawSpatialData()
  mapReady.value = true
  resizeObserver = new ResizeObserver(() => map?.invalidateSize({ animate: false }))
  resizeObserver.observe(mapHost.value)
})

watch(() => [props.center, props.bounds, props.markers, props.areas, props.selectedId, props.hoveredId], () => drawSpatialData(), { deep: true })

onBeforeUnmount(() => {
  if (tileStatusTimer) clearTimeout(tileStatusTimer)
  resizeObserver?.disconnect()
  map?.remove()
  map = undefined
})
</script>

<template>
  <div class="relative isolate overflow-hidden rounded-xl border border-cyan-300/15 bg-[#061019]" :style="{ height }">
    <div v-if="hasSpatialData" ref="mapHost" class="absolute inset-0 z-0" />
    <div v-else class="absolute inset-0 grid place-items-center bg-[radial-gradient(circle_at_center,rgba(34,211,238,.08),transparent_58%)]">
      <div class="max-w-xs px-6 text-center">
        <SafeIcon name="MapPinned" :size="28" class="mx-auto text-slate-600" />
        <p class="mt-3 text-xs font-medium text-slate-300">等待空间成果</p>
        <p class="mt-1 text-[10px] leading-5 text-slate-500">带坐标的影像或点云完成解析后，将自动定位到真实地图</p>
      </div>
    </div>

    <div v-if="hasSpatialData" class="pointer-events-none absolute left-3 top-3 z-[500] flex items-center gap-2 rounded-lg border border-white/10 bg-[#07111f]/88 px-2.5 py-1.5 text-[10px] text-slate-300 shadow-lg backdrop-blur">
      <span class="h-1.5 w-1.5 rounded-full" :class="tileReady ? 'bg-emerald-300' : 'animate-pulse bg-amber-300'" />
      {{ tileStatusLabel }}
    </div>
    <div v-if="hasSpatialData && !compact" class="pointer-events-none absolute bottom-6 left-3 z-[500] rounded-lg border border-white/10 bg-[#07111f]/85 px-2.5 py-1.5 font-mono text-[9px] text-cyan-100 backdrop-blur">
      {{ validCenter?.longitude.toFixed(6) }}, {{ validCenter?.latitude.toFixed(6) }}
    </div>
    <div v-if="mapReady && markers.length" class="pointer-events-none absolute right-3 top-3 z-[500] rounded-lg border border-white/10 bg-[#07111f]/88 px-2.5 py-1.5 text-[9px] text-slate-300 backdrop-blur">
      {{ markers.length }} 个空间目标
    </div>
  </div>
</template>

<style>
.hg-spatial-marker { background: transparent; border: 0; }
.hg-spatial-marker > span { position: relative; display: block; width: var(--size); height: var(--size); border: 2px solid rgba(255,255,255,.92); border-radius: 999px; background: var(--marker); box-shadow: 0 0 0 5px color-mix(in srgb, var(--marker) 22%, transparent), 0 4px 16px rgba(0,0,0,.45); }
.hg-spatial-marker > span::after { content: ''; position: absolute; inset: -8px; border: 1px solid var(--marker); border-radius: 999px; opacity: 0; }
.hg-spatial-marker > span.is-selected::after { animation: hg-map-pulse 1.8s ease-out infinite; }
.hg-spatial-marker > span.is-hovered { filter: brightness(1.18); }
.hg-spatial-marker i { position: absolute; inset: 4px; border-radius: inherit; background: rgba(255,255,255,.8); }
.leaflet-container { background: #07111f; font-family: inherit; }
.leaflet-tile-pane { filter: saturate(.78) brightness(.72) contrast(1.06); }
.leaflet-control-attribution { background: rgba(7,17,31,.78) !important; color: #94a3b8; font-size: 8px !important; }
.leaflet-control-attribution a { color: #67e8f9; }
.leaflet-control-zoom a { border-color: rgba(255,255,255,.1) !important; background: rgba(7,17,31,.88) !important; color: #cbd5e1 !important; }
.leaflet-tooltip { border: 1px solid rgba(103,232,249,.2); background: rgba(7,17,31,.94); color: #e2e8f0; box-shadow: 0 8px 24px rgba(0,0,0,.35); font-size: 11px; }
@keyframes hg-map-pulse { from { transform: scale(.55); opacity: .7; } to { transform: scale(1.35); opacity: 0; } }
</style>

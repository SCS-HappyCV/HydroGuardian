<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { Map as LeafletMap, Marker } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { IonContent, IonIcon, IonPage, IonSpinner } from '@ionic/vue'
import { checkmarkCircleOutline, locateOutline, navigateOutline } from 'ionicons/icons'
import { useRouter } from 'vue-router'
import MobileHeader from '@/components/MobileHeader.vue'
import { taskDetailPath } from '@/router/paths'
import { useWorkorderStore } from '@/stores/workorders'
import { LocationCaptureError, locationService } from '@/services/locationService'
import { navigationService } from '@/services/navigationService'

const router = useRouter()
const route = useRoute()
const store = useWorkorderStore()
const visibleItems = computed(() => store.items.filter((item) => item.status !== 'closed'))
const nearestItem = computed(() => [...visibleItems.value].sort((a, b) => a.distanceMeters - b.distanceMeters)[0])
const focusedItem = computed(() => {
  const taskId = String(route.query.task || '')
  return visibleItems.value.find((item) => item.id === taskId) || nearestItem.value
})
const locating = ref(false)
const locationAccuracy = ref<number | null>(null)
const locationError = ref('')
const navigationError = ref('')
const mapHost = ref<HTMLElement | null>(null)
const tileReady = ref(false)
const tileError = ref(false)
const liveTilesReady = ref(false)
const mapReady = ref(false)
let map: LeafletMap | undefined
let leaflet: typeof import('leaflet') | undefined
let mapMarkers: Marker[] = []
let liveTileLayer: import('leaflet').TileLayer | undefined
let tileTimer: ReturnType<typeof setTimeout> | undefined

const positionedItems = computed(() => {
  const valid = visibleItems.value.filter((item) => item.longitude && item.latitude)
  if (!valid.length) return visibleItems.value.map((item, index) => ({ item, left: 32 + index * 18, top: 29 + index * 18 }))
  const longitudes = valid.map((item) => item.longitude)
  const latitudes = valid.map((item) => item.latitude)
  const west = Math.min(...longitudes)
  const east = Math.max(...longitudes)
  const south = Math.min(...latitudes)
  const north = Math.max(...latitudes)
  return valid.map((item) => ({
    item,
    left: 16 + ((item.longitude - west) / Math.max(east - west, 0.00001)) * 68,
    top: 18 + ((north - item.latitude) / Math.max(north - south, 0.00001)) * 58,
  }))
})

function openNavigation() {
  if (!nearestItem.value) return
  navigationError.value = ''
  try {
    navigationService.open(nearestItem.value.latitude, nearestItem.value.longitude, nearestItem.value.title)
  } catch (error) {
    navigationError.value = error instanceof Error ? error.message : '无法打开导航'
  }
}

function redrawMap() {
  if (!map || !leaflet) return
  mapMarkers.forEach((marker) => marker.remove())
  mapMarkers = []
  const L = leaflet
  visibleItems.value.forEach((item) => {
    if (!item.latitude || !item.longitude) return
    const selected = item.id === String(route.query.task || '')
    const color = item.riskLevel === 'high' ? '#fb7185' : '#a78bfa'
    const icon = L.divIcon({ className: 'mobile-map-marker', html: `<span class="${selected ? 'is-selected' : ''}" style="--marker:${color}"><b>${item.confidence}</b></span>`, iconSize: [34, 34], iconAnchor: [17, 17] })
    const marker = L.marker([item.latitude, item.longitude], { icon }).addTo(map!)
      .bindTooltip(`<strong>${item.title}</strong><br><span>${item.area} · ${item.distanceMeters} 米</span>`, { direction: 'top' })
      .on('click', () => router.push(taskDetailPath(item.id)))
    mapMarkers.push(marker)
  })
  if (focusedItem.value?.latitude && focusedItem.value.longitude) map.setView([focusedItem.value.latitude, focusedItem.value.longitude], route.query.task ? 16 : 12, { animate: false })
  else if (mapMarkers.length) map.fitBounds(L.featureGroup(mapMarkers).getBounds().pad(0.25), { maxZoom: 16 })
}

async function locateCurrentPosition() {
  locating.value = true
  locationError.value = ''
  try {
    const position = await locationService.capture()
    locationAccuracy.value = position.accuracy
  } catch (error) {
    locationError.value = error instanceof LocationCaptureError ? error.message : '定位失败，请稍后重试'
  } finally {
    locating.value = false
  }
}

onMounted(async () => {
  await nextTick()
  if (!mapHost.value) return
  leaflet = await import('leaflet')
  const cachedBounds = leaflet.latLngBounds([23.565, 109.625], [23.64, 109.695])
  map = leaflet.map(mapHost.value, {
    zoomControl: false,
    attributionControl: false,
    minZoom: 12,
    maxBounds: cachedBounds,
    maxBoundsViscosity: 1,
  }).setView([23.60, 109.66], 12)
  leaflet.control.zoom({ position: 'bottomright' }).addTo(map)
  let successfulTileCount = 0
  liveTileLayer = leaflet.tileLayer('/maps/osm/{z}/{x}/{y}.png', {
    maxNativeZoom: 17,
    maxZoom: 20,
    keepBuffer: 3,
    updateWhenIdle: true,
  })
    .on('tileload', () => { successfulTileCount += 1 })
    .on('load', () => { if (successfulTileCount > 0) { liveTilesReady.value = true; tileError.value = false } })
    .on('tileerror', () => { if (!tileReady.value) tileError.value = true })
    .addTo(map)
  tileTimer = setTimeout(() => {
    if (!tileReady.value) tileError.value = true
  }, 5000)
  mapReady.value = true
  redrawMap()
})
watch([visibleItems, () => route.query.task], redrawMap, { deep: true })
onBeforeUnmount(() => { if (tileTimer) clearTimeout(tileTimer); liveTileLayer?.remove(); mapMarkers.forEach((marker) => marker.remove()); map?.remove(); map = undefined })
</script>

<template>
  <IonPage>
    <MobileHeader title="风险地图" subtitle="现场任务空间分布" />
    <IonContent>
      <div class="map-page">
        <div class="map-canvas" :class="{ 'is-ready': mapReady }">
          <img class="cached-map-image" src="/maps/guigang-task-area.jpg" alt="任务区域真实地图" @load="tileReady = true; tileError = false" @error="tileError = true">
          <div ref="mapHost" class="map-leaflet" />
          <div class="map-vignette" />
          <div v-if="!tileReady" class="map-loading">{{ tileError ? '地图底图服务不可达 · 请检查网络' : '正在加载真实地图…' }}</div>
          <div class="current"><IonIcon :icon="locateOutline" /></div>
          <button class="locate" :disabled="locating" aria-label="定位当前位置" @click="locateCurrentPosition">
            <IonSpinner v-if="locating" name="crescent" />
            <IonIcon v-else :icon="locateOutline" />
          </button>
        </div>
        <div v-if="locationAccuracy !== null || locationError" class="locate-status surface" :class="{ error: locationError }">
          <IonIcon :icon="locationError ? locateOutline : checkmarkCircleOutline" />
          <span>{{ locationError || `当前位置已更新 · 精度 ${locationAccuracy} 米` }}</span>
        </div>
        <div v-if="navigationError" class="navigation-error surface">{{ navigationError }}</div>
          <div v-if="focusedItem" class="nearby surface">
          <div><span class="eyebrow">{{ focusedItem.id === nearestItem?.id ? '最近任务' : '当前任务' }}</span><strong>{{ focusedItem.title }}</strong><small>{{ focusedItem.distanceMeters }} 米 · {{ focusedItem.area }}</small></div>
          <button @click="navigationService.open(focusedItem.latitude, focusedItem.longitude, focusedItem.title)"><IonIcon :icon="navigateOutline" />导航</button>
        </div>
      </div>
    </IonContent>
  </IonPage>
</template>

<style scoped>
.map-page { position: relative; height: 100%; min-height: 620px; }
.map-canvas { position: absolute; inset: 0; overflow: hidden; background: #07111f; }
.cached-map-image { position: absolute; z-index: 0; inset: 0; display: block; width: 100%; height: 100%; opacity: .72; object-fit: cover; filter: saturate(.82) brightness(.72) contrast(1.12); }
.map-leaflet { position: absolute; z-index: 1; inset: 0; background: transparent; }
.map-vignette { position: absolute; z-index: 2; inset: 0; pointer-events: none; background: linear-gradient(180deg, rgba(7,17,31,.22), transparent 18%, transparent 70%, rgba(7,17,31,.78)); box-shadow: inset 0 0 70px rgba(4,12,22,.28); }
.map-loading { position: absolute; z-index: 500; top: 13px; left: 13px; border: 1px solid rgba(148,180,208,.15); border-radius: 9px; background: rgba(7,17,31,.88); padding: 8px 10px; color: #f4c86a; font-size: 9px; }
.marker { position: absolute; display: grid; width: 38px; height: 38px; transform: translate(-50%, -50%); place-items: center; border: 2px solid currentColor; border-radius: 50% 50% 50% 4px; color: white; rotate: -45deg; box-shadow: 0 0 22px currentColor; }
.marker span { rotate: 45deg; font-size: 9px; font-weight: 800; }
.marker-high { background: #ff5d5d; color: #ff837c; }
.marker-review { background: #8b7cff; color: #b8adff; }
.current { position: absolute; z-index: 3; left: 48%; top: 48%; display: grid; width: 28px; height: 28px; place-items: center; border: 5px solid rgba(255,255,255,.7); border-radius: 50%; background: #2f80ed; color: white; box-shadow: 0 0 0 12px rgba(47,128,237,.17); }
.locate { position: absolute; z-index: 3; right: 15px; bottom: 140px; display: grid; width: 43px; height: 43px; place-items: center; border: 1px solid rgba(148,180,208,.15); border-radius: 13px; background: #0a1929; color: #55d8df; font-size: 20px; }
.locate ion-spinner { width: 19px; }
.locate-status { position: absolute; top: 12px; right: 13px; left: 13px; display: flex; align-items: center; gap: 6px; padding: 9px 11px; color: #63e3af; font-size: 9px; }
.locate-status.error { color: #ff9a94; }
.navigation-error { position: absolute; top: 58px; right: 13px; left: 13px; padding: 9px 11px; color: #ff9a94; font-size: 9px; }
.nearby { position: absolute; right: 13px; bottom: 17px; left: 13px; display: flex; align-items: center; justify-content: space-between; padding: 14px; }
.nearby strong, .nearby small { display: block; }
.nearby strong { margin-top: 5px; font-size: 12px; }
.nearby small { margin-top: 4px; color: #71849a; font-size: 9px; }
.nearby button { display: flex; align-items: center; gap: 5px; border: 0; border-radius: 10px; background: #2f80ed; padding: 10px 13px; color: white; font-size: 10px; }
</style>

<style>
.mobile-map-marker { background: transparent; border: 0; }
.mobile-map-marker span { display: grid; width: 34px; height: 34px; place-items: center; border: 2px solid rgba(255,255,255,.92); border-radius: 50% 50% 50% 4px; transform: rotate(-45deg); background: var(--marker); color: #fff; box-shadow: 0 0 16px var(--marker); }
.mobile-map-marker b { transform: rotate(45deg); font-size: 9px; }
.mobile-map-marker span.is-selected { box-shadow: 0 0 0 7px color-mix(in srgb, var(--marker) 24%, transparent), 0 0 22px var(--marker); }
.map-canvas .leaflet-container { width: 100%; height: 100%; background: transparent; font-family: inherit; }
.map-canvas .leaflet-tile-pane { filter: saturate(.9) brightness(.86) contrast(1.08); }
.map-canvas .leaflet-tile { opacity: 1 !important; mix-blend-mode: normal !important; }
.map-canvas .leaflet-tile:not(.leaflet-tile-loaded) { visibility: hidden !important; }
.map-canvas .leaflet-control-attribution { background: rgba(7,17,31,.78) !important; color: #94a3b8; font-size: 8px !important; }
.map-canvas .leaflet-control-attribution a { color: #67e8f9; }
.map-canvas .leaflet-control-zoom a { border-color: rgba(255,255,255,.1) !important; background: rgba(7,17,31,.88) !important; color: #cbd5e1 !important; }
</style>

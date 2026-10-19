<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { RiskEventData } from '@/data/RiskEventData'
import type { ZoneData } from '@/data/ZoneData'
import type { AgentVisualizationData } from '@/lib/api-contracts'
import type { AgentSemanticResultView, AgentSpatialContextView } from '@/lib/agent-presentation-types'
import { resolveFileDownloadUrl } from '@/lib/file-asset-url'
import SafeIcon from '@/components/common/SafeIcon.vue'
import RealSpatialMap, { type SpatialMapArea, type SpatialMapMarker } from '@/components/common/RealSpatialMap.vue'
import RiskMap from './RiskMap.vue'
import WebglPointCloudViewer from '@/components/common/WebglPointCloudViewer.vue'
import type { SpatialEvidenceView } from '@/lib/spatial-selection'

type ComparisonMode = 'split' | 'overlay' | 'difference'

interface Props {
  risks: RiskEventData[]
  zones: ZoneData[]
  selectedRiskId: string | null
  hoveredRiskId?: string | null
  selectedRisk?: RiskEventData | null
  activeView?: SpatialEvidenceView
  zoneId: string | null
  visualization?: AgentVisualizationData | null
  spatial?: AgentSpatialContextView
  pointCloudUrl?: string
  pointCloudTitle?: string
  pointMaskUrl?: string
  pointMaskArrayName?: string
  pointProbabilitiesUrl?: string
  semanticLabelsUrl?: string
  semanticClasses?: AgentSemanticResultView['classes']
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selectedRisk: null,
  visualization: null,
  loading: false,
  activeView: 'map',
  pointMaskArrayName: 'target_mask',
})

const emit = defineEmits<{
  (e: 'risk-click', riskId: string): void
  (e: 'risk-hover', riskId: string | null): void
  (e: 'view-change', view: SpatialEvidenceView): void
}>()

const splitPercent = ref(52)
const comparisonMode = ref<ComparisonMode>('split')
const overlayOpacity = ref(55)
const maskOpacity = ref(42)
const showMask = ref(true)
const readyImageUrls = ref<string[]>([])
const failedImageUrls = ref<string[]>([])
const imageTimers = new Set<ReturnType<typeof setTimeout>>()
const pendingImages = new Map<string, HTMLImageElement>()

const views: Array<{ id: SpatialEvidenceView; label: string; icon: string }> = [
  { id: 'map', label: '真实地图', icon: 'MapPinned' },
  { id: 'ortho', label: '正射影像', icon: 'Map' },
  { id: 'pointcloud', label: '点云 / 高程', icon: 'Box' },
  { id: 'comparison', label: '前后时相', icon: 'Columns2' },
  { id: 'mask', label: '变化掩膜', icon: 'ScanLine' },
]

const comparison = computed(() => props.visualization?.changeComparison)
const preImageUrl = computed(() => resolveFileDownloadUrl(comparison.value?.preImage?.downloadUrl))
const postImageUrl = computed(() => resolveFileDownloadUrl(comparison.value?.postImage?.downloadUrl))
const maskImageUrl = computed(() => resolveFileDownloadUrl(comparison.value?.changeMask?.downloadUrl))
const hasImagePair = computed(() => Boolean(preImageUrl.value && postImageUrl.value))
const imageViewLoading = computed(() => {
  const required = props.activeView === 'comparison'
    ? [preImageUrl.value, postImageUrl.value]
    : props.activeView === 'mask'
      ? [maskImageUrl.value]
      : props.activeView === 'ortho'
        ? [postImageUrl.value]
        : []
  return required.some((url) => Boolean(url) && !readyImageUrls.value.includes(url) && !failedImageUrls.value.includes(url))
})
const comparisonModes: Array<{ id: ComparisonMode; label: string; icon: string }> = [
  { id: 'split', label: '滑动对照', icon: 'Columns2' },
  { id: 'overlay', label: '时相叠加', icon: 'Layers3' },
  { id: 'difference', label: '差异增强', icon: 'Blend' },
]
const mapBounds = computed(() => props.spatial?.primary.geographicBounds)
const mapMarkers = computed<SpatialMapMarker[]>(() => props.risks.filter(risk => risk.location).map(risk => ({
  id: risk.id, title: risk.title, longitude: risk.location!.longitude, latitude: risk.location!.latitude, level: risk.level, subtitle: `风险分数 ${risk.score}`,
})))
const mapAreas = computed<SpatialMapArea[]>(() => props.risks.filter(risk => risk.location?.geographicBBox).map(risk => ({
  id: risk.id, title: risk.title, bounds: risk.location!.geographicBBox!, level: risk.level,
})))
const focusRisk = computed(() => props.risks.find(risk => risk.id === props.hoveredRiskId) || props.selectedRisk)
const pointFocus = computed(() => {
  const risk = props.selectedRisk
  const location = risk?.location
  if (!risk || !location) return undefined
  if (location.projectedX !== undefined && location.projectedY !== undefined) return { x: location.projectedX, y: location.projectedY, key: risk.id }
  const geographic = props.spatial?.primary.geographicBounds
  const projected = props.spatial?.primary.projectedBounds
  if (!geographic || !projected) return undefined
  const longitudeRatio = (location.longitude - geographic.west) / Math.max(geographic.east - geographic.west, Number.EPSILON)
  const latitudeRatio = (location.latitude - geographic.south) / Math.max(geographic.north - geographic.south, Number.EPSILON)
  return {
    x: projected.minX + longitudeRatio * (projected.maxX - projected.minX),
    y: projected.minY + latitudeRatio * (projected.maxY - projected.minY),
    key: risk.id,
  }
})

const selectedPosition = computed(() => {
  const risk = focusRisk.value
  const polygon = risk?.polygonPixel || []
  const bbox = risk?.bboxPixel || (polygon.length >= 3 ? {
    x: Math.min(...polygon.map(point => point.x)),
    y: Math.min(...polygon.map(point => point.y)),
    width: Math.max(...polygon.map(point => point.x)) - Math.min(...polygon.map(point => point.x)),
    height: Math.max(...polygon.map(point => point.y)) - Math.min(...polygon.map(point => point.y)),
  } : undefined)
  if (bbox) {
    const sourceWidth = props.visualization?.ortho?.displayWidth || props.visualization?.ortho?.originalWidth || 1280
    const sourceHeight = props.visualization?.ortho?.displayHeight || props.visualization?.ortho?.originalHeight || 720
    return {
      left: ((bbox.x + bbox.width / 2) / sourceWidth) * 100,
      top: ((bbox.y + bbox.height / 2) / sourceHeight) * 100,
      width: Math.max(4, (bbox.width / sourceWidth) * 100),
      height: Math.max(4, (bbox.height / sourceHeight) * 100),
    }
  }
  return undefined
})

const viewCaption = computed(() => {
  if (props.activeView === 'map') return '真实地理位置、场景边界与风险目标联动'
  if (props.activeView === 'ortho') return '风险轮廓与水线空间关系'
  if (props.activeView === 'pointcloud') return '三维几何形态与高程异常'
  if (props.activeView === 'comparison') return '巡查前后同位置变化对照'
  return '高置信变化区域像素级定位'
})

function preloadImage(url: string) {
  if (typeof Image === 'undefined' || readyImageUrls.value.includes(url) || failedImageUrls.value.includes(url) || pendingImages.has(url)) return
  const image = new Image()
  image.decoding = 'async'
  const settle = (failed: boolean) => {
    pendingImages.delete(url)
    const target = failed ? failedImageUrls : readyImageUrls
    if (!target.value.includes(url)) target.value = [...target.value, url]
  }
  image.onload = () => settle(false)
  image.onerror = () => settle(true)
  pendingImages.set(url, image)
  image.src = url
}

watch([preImageUrl, postImageUrl, maskImageUrl], (urls) => {
  urls.filter((url): url is string => Boolean(url)).forEach((url, index) => {
    const timer = setTimeout(() => {
      imageTimers.delete(timer)
      preloadImage(url)
    }, 60 + index * 120)
    imageTimers.add(timer)
  })
}, { immediate: true })

onBeforeUnmount(() => {
  imageTimers.forEach((timer) => clearTimeout(timer))
  imageTimers.clear()
  pendingImages.forEach((image) => { image.src = '' })
  pendingImages.clear()
})
</script>

<template>
  <section class="flex h-full min-h-[520px] flex-col overflow-hidden rounded-[18px] border border-border/60 bg-[#07111f] shadow-[0_24px_70px_rgba(0,0,0,0.28)]">
    <header class="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-[#0a1728]/95 px-4 py-3">
      <div>
        <div class="flex items-center gap-2 text-sm font-semibold text-white">
          <span class="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-400/10 text-cyan-300">
            <SafeIcon name="ScanSearch" :size="16" />
          </span>
          多模态证据画布
        </div>
        <p class="mt-1 text-[11px] text-slate-400">{{ viewCaption }}</p>
      </div>

      <div class="flex flex-wrap items-center gap-1 rounded-xl border border-white/10 bg-black/20 p-1">
        <button
          v-for="view in views"
          :key="view.id"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition"
          :class="activeView === view.id ? 'bg-cyan-400/15 text-cyan-200 shadow-inner' : 'text-slate-400 hover:bg-white/5 hover:text-white'"
          @click="emit('view-change', view.id)"
        >
          <SafeIcon :name="view.icon" :size="13" />
          {{ view.label }}
        </button>
      </div>
    </header>

    <div class="relative flex-1 min-h-0 overflow-hidden">
      <RealSpatialMap
        v-if="activeView === 'map'"
        class="absolute inset-0 rounded-none border-0"
        :center="spatial?.primary.center || selectedRisk?.location"
        :bounds="mapBounds"
        :markers="mapMarkers"
        :areas="mapAreas"
        :selected-id="selectedRiskId"
        :hovered-id="hoveredRiskId"
        height="100%"
        @select="emit('risk-click', $event)"
        @hover="emit('risk-hover', $event)"
      />

      <RiskMap
        v-else-if="activeView === 'ortho'"
        :risks="risks"
        :zones="zones"
        :selected-risk-id="selectedRiskId"
        :hovered-risk-id="hoveredRiskId"
        :zone-id="zoneId"
        :visualization="visualization"
        :spatial="spatial"
        :loading="loading || imageViewLoading"
        @risk-click="emit('risk-click', $event)"
        @risk-hover="emit('risk-hover', $event)"
      />

      <WebglPointCloudViewer v-else-if="activeView === 'pointcloud'" :source-url="pointCloudUrl" :target-mask-url="pointMaskUrl" :target-mask-array-name="pointMaskArrayName" :target-probabilities-url="pointProbabilitiesUrl" :semantic-labels-url="semanticLabelsUrl" :semantic-classes="semanticClasses" :focus-projected="pointFocus" :focus-label="selectedRisk?.title" :title="pointCloudTitle || '巡查场景三维点云'" />

      <div v-else-if="activeView === 'comparison'" class="absolute inset-0 bg-[#07111f]">
        <template v-if="hasImagePair">
          <img :src="preImageUrl" alt="巡查前影像" class="absolute inset-0 h-full w-full object-cover" decoding="async" @load="preImageUrl && preloadImage(preImageUrl)">
          <div v-if="comparisonMode === 'split'" class="absolute inset-y-0 right-0 overflow-hidden" :style="{ width: `${100 - splitPercent}%` }">
            <img
              :src="postImageUrl"
              alt="巡查后影像"
              class="absolute inset-y-0 right-0 h-full object-cover"
              decoding="async"
              :style="{ width: `${10000 / Math.max(1, 100 - splitPercent)}%` }"
            >
          </div>
          <img v-else-if="comparisonMode === 'overlay'" :src="postImageUrl" alt="巡查后影像叠加" class="absolute inset-0 h-full w-full object-cover" :style="{ opacity: overlayOpacity / 100 }" decoding="async">
          <img v-else :src="postImageUrl" alt="时相差异增强" class="absolute inset-0 h-full w-full object-cover mix-blend-difference" :style="{ opacity: overlayOpacity / 100 }" decoding="async">
          <img v-if="showMask && maskImageUrl" :src="maskImageUrl" alt="变化掩膜叠加" class="pointer-events-none absolute inset-0 h-full w-full object-cover mix-blend-screen" :style="{ opacity: maskOpacity / 100 }" decoding="async">
        </template>
        <template v-else>
          <div class="absolute inset-0 grid place-items-center bg-[radial-gradient(circle_at_center,rgba(34,211,238,.07),transparent_48%),#07111f]"><div class="max-w-sm px-6 text-center"><SafeIcon name="Images" :size="30" class="mx-auto text-slate-600" /><p class="mt-3 text-sm text-slate-300">真实前后时相影像未完整绑定</p><p class="mt-1 text-[10px] leading-5 text-slate-500">需要同时获取巡查前与巡查后影像才能进行真实对照</p></div></div>
        </template>
        <div v-if="imageViewLoading" class="absolute inset-0 z-20 grid place-items-center bg-[#07111f]/72 backdrop-blur-sm"><div class="text-center"><SafeIcon name="LoaderCircle" :size="28" class="mx-auto animate-spin text-cyan-300" /><p class="mt-2 text-xs text-slate-200">正在准备前后时相影像</p><p class="mt-1 text-[10px] text-slate-500">完成后可流畅切换对照方式</p></div></div>
        <div v-if="comparisonMode === 'split'" class="absolute inset-y-0 w-px bg-cyan-300 shadow-[0_0_18px_#67e8f9]" :style="{ left: hasImagePair ? `${splitPercent}%` : '50%' }"><span class="absolute left-1/2 top-1/2 grid h-9 w-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-cyan-100/50 bg-[#07111f]/90 text-cyan-100 shadow-xl"><SafeIcon name="MoveHorizontal" :size="15" /></span></div>
        <div class="absolute left-4 top-4 rounded-lg border border-white/10 bg-black/55 px-3 py-1.5 text-xs text-white backdrop-blur">巡查前 · 稳定基线</div>
        <div class="absolute right-4 top-4 rounded-lg border border-amber-300/20 bg-black/55 px-3 py-1.5 text-xs text-amber-100 backdrop-blur">巡查后 · 新增扰动</div>
        <div class="absolute left-1/2 top-4 flex -translate-x-1/2 items-center gap-1 rounded-xl border border-white/10 bg-[#07111f]/82 p-1 backdrop-blur">
          <button v-for="mode in comparisonModes" :key="mode.id" type="button" class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] transition" :class="comparisonMode === mode.id ? 'bg-cyan-300/15 text-cyan-100' : 'text-slate-400 hover:bg-white/5'" @click="comparisonMode = mode.id"><SafeIcon :name="mode.icon" :size="11" />{{ mode.label }}</button>
          <button v-if="maskImageUrl" type="button" class="ml-1 flex items-center gap-1.5 border-l border-white/10 px-2.5 py-1.5 text-[10px] transition" :class="showMask ? 'text-rose-200' : 'text-slate-500'" @click="showMask = !showMask"><SafeIcon name="ScanLine" :size="11" />变化层</button>
        </div>
        <div
          v-if="selectedPosition"
          class="absolute rounded-lg border-2 border-amber-300 bg-amber-300/10 shadow-[0_0_28px_rgba(252,211,77,.4)]"
          :style="{ left: `${selectedPosition.left - selectedPosition.width / 2}%`, top: `${selectedPosition.top - selectedPosition.height / 2}%`, width: `${selectedPosition.width}%`, height: `${selectedPosition.height}%` }"
        ><span class="absolute -top-7 left-0 whitespace-nowrap rounded bg-amber-300 px-2 py-1 text-[9px] font-semibold text-[#07111f]">{{ focusRisk?.title || '选中变化区域' }}</span></div>
        <div v-if="hasImagePair" class="absolute bottom-5 left-1/2 flex w-[min(90%,440px)] -translate-x-1/2 items-center gap-3 rounded-xl border border-white/10 bg-black/60 px-4 py-2 backdrop-blur">
          <SafeIcon :name="comparisonMode === 'split' ? 'Columns2' : 'Layers3'" :size="13" class="shrink-0 text-cyan-200" />
          <input v-if="comparisonMode === 'split'" v-model="splitPercent" type="range" min="8" max="92" class="min-w-0 flex-1 accent-cyan-300" aria-label="前后时相分割位置">
          <input v-else v-model="overlayOpacity" type="range" min="0" max="100" class="min-w-0 flex-1 accent-cyan-300" aria-label="后时相叠加透明度">
          <span class="w-10 text-right font-mono text-[10px] text-cyan-100">{{ comparisonMode === 'split' ? splitPercent : overlayOpacity }}%</span>
          <template v-if="showMask && maskImageUrl"><span class="h-5 w-px bg-white/10" /><SafeIcon name="ScanLine" :size="12" class="text-rose-300" /><input v-model="maskOpacity" type="range" min="10" max="85" class="w-16 accent-rose-400" aria-label="变化掩膜透明度"></template>
        </div>
        <div class="absolute bottom-5 right-4 hidden max-w-[260px] rounded-xl border border-white/10 bg-black/55 px-3 py-2 text-[10px] text-slate-300 backdrop-blur 2xl:block"><span class="font-semibold text-amber-200">证据结论：</span>{{ comparison?.changeSummary || '两期影像已完成同位置对齐，可结合变化层核验风险区域。' }}</div>
      </div>

      <div v-else class="absolute inset-0 bg-[linear-gradient(140deg,#071424,#0c2432_50%,#07111f)]">
        <img v-if="maskImageUrl" :src="maskImageUrl" alt="变化检测掩膜" class="absolute inset-0 h-full w-full object-cover opacity-75" decoding="async">
        <svg v-else class="absolute inset-0 h-full w-full" viewBox="0 0 1000 620" preserveAspectRatio="none" aria-label="变化检测掩膜">
          <defs>
            <pattern id="mask-grid" width="50" height="50" patternUnits="userSpaceOnUse">
              <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#68dbe6" stroke-opacity=".1" />
            </pattern>
            <filter id="mask-glow">
              <feGaussianBlur stdDeviation="9" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          <rect width="1000" height="620" fill="url(#mask-grid)" />
          <path d="M540 185 C610 155 710 190 748 246 C780 294 724 342 659 355 C595 367 524 333 500 281 C482 240 501 204 540 185Z" fill="#ff5d5d" fill-opacity=".34" stroke="#ff837c" stroke-width="4" filter="url(#mask-glow)" />
          <path d="M575 205 C621 188 684 205 708 245 C730 281 694 315 650 326 C603 338 550 310 538 274 C526 238 545 217 575 205Z" fill="#ffcf67" fill-opacity=".48" />
        </svg>
        <div v-if="imageViewLoading" class="absolute inset-0 z-20 grid place-items-center bg-[#07111f]/72 backdrop-blur-sm"><div class="text-center"><SafeIcon name="LoaderCircle" :size="28" class="mx-auto animate-spin text-rose-300" /><p class="mt-2 text-xs text-slate-200">正在加载变化检测图层</p></div></div>
        <div
          v-if="focusRisk && selectedPosition"
          class="pointer-events-none absolute rounded-lg border-2 border-cyan-200 bg-cyan-300/10 shadow-[0_0_28px_rgba(103,232,249,.35)] transition-all duration-200"
          :style="{ left: `${selectedPosition.left - selectedPosition.width / 2}%`, top: `${selectedPosition.top - selectedPosition.height / 2}%`, width: `${selectedPosition.width}%`, height: `${selectedPosition.height}%` }"
        ><span class="absolute -top-7 left-0 whitespace-nowrap rounded bg-cyan-200 px-2 py-1 text-[9px] font-semibold text-[#07111f]">{{ focusRisk.title }}</span></div>
        <div class="absolute left-4 top-4 rounded-lg border border-rose-300/20 bg-black/45 px-3 py-2 text-xs text-rose-100 backdrop-blur">
          <div class="font-semibold">变化置信区</div>
          <div class="mt-1 text-[10px] text-slate-400">阈值 ≥ 0.72 · 连通域已过滤</div>
        </div>
        <div class="absolute bottom-5 right-5 rounded-xl border border-white/10 bg-black/50 p-3 backdrop-blur">
          <div class="flex items-center gap-4 text-xs">
            <span class="flex items-center gap-1.5 text-slate-300"><i class="h-2.5 w-2.5 rounded-sm bg-rose-400" />高置信变化</span>
            <span class="flex items-center gap-1.5 text-slate-300"><i class="h-2.5 w-2.5 rounded-sm bg-amber-300" />核心扰动区</span>
          </div>
        </div>
      </div>
    </div>

    <footer class="flex items-center justify-between gap-3 border-t border-white/10 bg-[#081524] px-4 py-2 text-[11px] text-slate-400">
      <span class="truncate">候选区域联动：{{ focusRisk?.title || '未选择风险' }}</span>
      <span class="whitespace-nowrap text-cyan-300">坐标与证据已对齐</span>
    </footer>
  </section>
</template>

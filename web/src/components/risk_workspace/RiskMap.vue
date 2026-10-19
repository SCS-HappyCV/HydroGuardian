<!-- 风险地图组件：展示正射图投影、风险框叠加和本地风险点兜底。 -->

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import type { RiskEventData } from '@/data/RiskEventData'
import type { ZoneData } from '@/data/ZoneData'
import type { AgentRiskOverlayData, AgentVisualizationData } from '@/lib/api-contracts'
import { resolveFileDownloadUrl } from '@/lib/file-asset-url'
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentSpatialContextView } from '@/lib/agent-presentation-types'
import { formatGeographicCoordinate } from '@/lib/spatial-location'

interface OverlayItem {
  overlay: AgentRiskOverlayData
  index: number
  riskId: string
  risk?: RiskEventData
}

interface Props {
  risks: RiskEventData[]
  zones: ZoneData[]
  selectedRiskId: string | null
  hoveredRiskId?: string | null
  zoneId: string | null
  visualization?: AgentVisualizationData | null
  spatial?: AgentSpatialContextView
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  visualization: null,
  loading: false,
})

const emit = defineEmits<{
  (e: 'risk-click', riskId: string): void
  (e: 'risk-hover', riskId: string | null): void
}>()

const ortho = computed(() => props.visualization?.ortho)
const overlays = computed(() => props.visualization?.riskOverlays || [])
const zoom = ref(1)
const cursorPixel = ref<{ x: number; y: number } | null>(null)

// 计算 SVG 画布宽度，缺少后端尺寸时使用稳定默认值。
const displayWidth = computed(() => {
  return Math.max(1, Number(ortho.value?.displayWidth || ortho.value?.originalWidth || 1280))
})

// 计算 SVG 画布高度，缺少后端尺寸时使用稳定默认值。
const displayHeight = computed(() => {
  return Math.max(1, Number(ortho.value?.displayHeight || ortho.value?.originalHeight || 720))
})

// 读取当前筛选区域名称，用于底部状态栏展示。
const currentZoneName = computed(() => {
  if (!props.zoneId) return '全部区域'
  return props.zones.find((zone) => zone.id === props.zoneId)?.name || props.zoneId
})

// 建立风险 ID 索引，支持 overlayId、riskCardId 和 regionId 多种后端关联键。
const riskLookup = computed(() => {
  const lookup = new Map<string, RiskEventData>()

  props.risks.forEach((risk) => {
    const keys = [
      risk.id,
      risk.overlayId,
      risk.riskCardId,
      risk.candidateRegionId,
      risk.templateId,
    ].filter((item): item is string => Boolean(item))

    keys.forEach((key) => lookup.set(key, risk))
  })

  return lookup
})

// 按风险等级分组，用于没有真实正射图时的预置点位兜底。
const risksByLevel = computed(() => {
  return {
    high: props.risks.filter((risk) => risk.level === 'high'),
    medium: props.risks.filter((risk) => risk.level === 'medium'),
    low: props.risks.filter((risk) => risk.level === 'low'),
    review_required: props.risks.filter((risk) => risk.level === 'review_required'),
  }
})

const orthoImageUrl = computed(() => resolveFileDownloadUrl(ortho.value?.sourceFile?.downloadUrl))
const hasAgentVisualization = computed(() => Boolean(orthoImageUrl.value || overlays.value.length > 0))

// 生成 overlay 的候选关联 ID，顺序与转换层保持一致。
function overlayCandidateIds(overlay: AgentRiskOverlayData, index: number): string[] {
  return [
    overlay.riskCardId,
    overlay.overlayId,
    overlay.regionId,
    `agent-risk-${index + 1}`,
  ].filter((item): item is string => Boolean(item))
}

// 查找 overlay 对应的前端风险 ID。
function riskIdForOverlay(overlay: AgentRiskOverlayData, index: number): string {
  const candidates = overlayCandidateIds(overlay, index)
  return candidates.find((candidate) => riskLookup.value.has(candidate)) || candidates[0] || `agent-risk-${index + 1}`
}

// 只展示当前筛选结果内仍然存在的风险框，保证地图、表格和筛选条件一致。
const overlayItems = computed<OverlayItem[]>(() => {
  return overlays.value
    .map((overlay, index) => {
      const riskId = riskIdForOverlay(overlay, index)
      return {
        overlay,
        index,
        riskId,
        risk: riskLookup.value.get(riskId),
      }
    })
    .filter((item) => Boolean(item.risk))
})

const selectedOverlay = computed(() => overlayItems.value.find((item) => item.riskId === props.selectedRiskId))
const selectedLocation = computed(() => selectedOverlay.value?.risk?.location)

function overlayCenter(item?: OverlayItem): { x: number; y: number } | undefined {
  const box = item?.overlay.bboxPixel
  if (box) return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
  const polygon = item?.overlay.polygonPixel || []
  if (!polygon.length) return undefined
  return {
    x: polygon.reduce((sum, point) => sum + point.x, 0) / polygon.length,
    y: polygon.reduce((sum, point) => sum + point.y, 0) / polygon.length,
  }
}

const mapViewBox = computed(() => {
  const width = displayWidth.value / zoom.value
  const height = displayHeight.value / zoom.value
  const selectedCenter = zoom.value > 1 ? overlayCenter(selectedOverlay.value) : undefined
  const centerX = selectedCenter?.x ?? displayWidth.value / 2
  const centerY = selectedCenter?.y ?? displayHeight.value / 2
  const x = Math.min(Math.max(0, centerX - width / 2), displayWidth.value - width)
  const y = Math.min(Math.max(0, centerY - height / 2), displayHeight.value - height)
  return `${x} ${y} ${width} ${height}`
})

const cursorLocation = computed(() => {
  const bounds = props.spatial?.primary?.geographicBounds
  if (!bounds || !cursorPixel.value) return undefined
  return {
    longitude: bounds.west + cursorPixel.value.x / displayWidth.value * (bounds.east - bounds.west),
    latitude: bounds.north - cursorPixel.value.y / displayHeight.value * (bounds.north - bounds.south),
  }
})

function handlePointerMove(event: PointerEvent) {
  const svg = event.currentTarget as SVGSVGElement
  const matrix = svg.getScreenCTM()
  if (!matrix) return
  const point = svg.createSVGPoint()
  point.x = event.clientX
  point.y = event.clientY
  const local = point.matrixTransform(matrix.inverse())
  cursorPixel.value = { x: local.x, y: local.y }
}

function zoomIn() {
  zoom.value = Math.min(4, Number((zoom.value * 1.5).toFixed(2)))
}

function zoomOut() {
  zoom.value = Math.max(1, Number((zoom.value / 1.5).toFixed(2)))
}

function focusSelected() {
  if (!selectedOverlay.value) return
  zoom.value = 2.5
}

function resetView() {
  zoom.value = 1
}

async function copySelectedCoordinate() {
  if (!selectedLocation.value) return
  try {
    await navigator.clipboard.writeText(formatGeographicCoordinate(selectedLocation.value))
    toast.success('风险坐标已复制')
  } catch {
    toast.error('坐标复制失败')
  }
}

// 判断 polygon 坐标是否足够绘制闭合区域。
function hasPolygon(overlay: AgentRiskOverlayData): boolean {
  return (overlay.polygonPixel || []).length >= 3
}

// 将后端 polygon 坐标转换为 SVG points 字符串。
function polygonPoints(overlay: AgentRiskOverlayData): string {
  return (overlay.polygonPixel || []).map((point) => `${point.x},${point.y}`).join(' ')
}

// 判断 bbox 坐标是否可用于绘制矩形框。
function hasBbox(overlay: AgentRiskOverlayData): boolean {
  const box = overlay.bboxPixel
  return Boolean(
    box
    && Number.isFinite(box.x)
    && Number.isFinite(box.y)
    && Number.isFinite(box.width)
    && Number.isFinite(box.height)
    && box.width > 0
    && box.height > 0,
  )
}

// 根据风险等级补齐叠加层颜色，后端返回颜色时优先使用后端值。
function overlayColor(item: OverlayItem): string {
  if (item.overlay.color) return item.overlay.color

  switch (item.risk?.level) {
    case 'high':
      return 'hsl(var(--destructive))'
    case 'medium':
      return 'hsl(var(--warning))'
    case 'low':
      return 'hsl(var(--success))'
    case 'review_required':
      return 'hsl(var(--accent))'
    default:
      return 'hsl(var(--primary))'
  }
}

// 判断当前 overlay 是否处于选中状态。
function isOverlaySelected(item: OverlayItem): boolean {
  return props.selectedRiskId === item.riskId
}

function isOverlayHovered(item: OverlayItem): boolean {
  return props.hoveredRiskId === item.riskId
}

// 处理地图风险点击，空 ID 会被忽略。
function handleRiskClick(riskId: string) {
  if (!riskId) return
  emit('risk-click', riskId)
}

watch([() => props.selectedRiskId, overlayItems], () => {
  if (selectedOverlay.value) zoom.value = 2.25
}, { immediate: true })
</script>

<template>
  <div class="w-full h-full flex flex-col bg-gradient-to-br from-muted/30 to-background relative overflow-hidden">
    <div class="flex-1 relative flex items-center justify-center min-h-0">
      <div v-if="loading" class="absolute inset-0 z-20 flex items-center justify-center bg-background/50 backdrop-blur-sm">
        <div class="flex items-center gap-2 text-sm text-muted-foreground">
          <SafeIcon name="Loader2" :size="18" class="animate-spin" />
          <span>加载智能体结果</span>
        </div>
      </div>

      <template v-if="hasAgentVisualization">
        <svg
          class="absolute inset-0 w-full h-full"
          :viewBox="mapViewBox"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="正射图风险叠加"
          @pointermove="handlePointerMove"
          @pointerleave="cursorPixel = null"
        >
          <defs>
            <pattern id="agent-map-grid" width="80" height="80" patternUnits="userSpaceOnUse">
              <path d="M 80 0 L 0 0 0 80" fill="none" stroke="currentColor" stroke-width="1" opacity="0.18" />
            </pattern>
          </defs>

          <rect :width="displayWidth" :height="displayHeight" fill="hsl(var(--muted))" opacity="0.35" />
          <rect :width="displayWidth" :height="displayHeight" fill="url(#agent-map-grid)" class="text-muted-foreground" />

          <image
            v-if="orthoImageUrl"
            :href="orthoImageUrl"
            x="0"
            y="0"
            :width="displayWidth"
            :height="displayHeight"
            preserveAspectRatio="none"
          />

          <g
            v-for="item in overlayItems"
            :key="item.riskId"
            class="cursor-pointer outline-none"
            tabindex="0"
            @click.stop="handleRiskClick(item.riskId)"
            @keydown.enter.prevent="handleRiskClick(item.riskId)"
            @pointerenter="emit('risk-hover', item.riskId)"
            @pointerleave="emit('risk-hover', null)"
            @focus="emit('risk-hover', item.riskId)"
            @blur="emit('risk-hover', null)"
          >
            <polygon
              v-if="hasPolygon(item.overlay)"
              :points="polygonPoints(item.overlay)"
              :style="{ stroke: overlayColor(item), fill: overlayColor(item) }"
              :stroke-width="isOverlaySelected(item) ? 6 : isOverlayHovered(item) ? 4.5 : 3"
              :fill-opacity="isOverlaySelected(item) ? 0.28 : isOverlayHovered(item) ? 0.22 : 0.16"
              stroke-linejoin="round"
            />
            <rect
              v-else-if="hasBbox(item.overlay)"
              :x="item.overlay.bboxPixel?.x"
              :y="item.overlay.bboxPixel?.y"
              :width="item.overlay.bboxPixel?.width"
              :height="item.overlay.bboxPixel?.height"
              :style="{ stroke: overlayColor(item), fill: overlayColor(item) }"
              :stroke-width="isOverlaySelected(item) ? 6 : isOverlayHovered(item) ? 4.5 : 3"
              :fill-opacity="isOverlaySelected(item) ? 0.28 : isOverlayHovered(item) ? 0.22 : 0.16"
              rx="4"
            />
          </g>
        </svg>

        <div v-if="!orthoImageUrl && !loading" class="pointer-events-none absolute inset-0 z-10 grid place-items-center">
          <div class="rounded-xl border border-amber-300/15 bg-[#07111f]/80 px-4 py-3 text-center shadow-xl backdrop-blur">
            <SafeIcon name="ImageOff" :size="22" class="mx-auto text-amber-200/80" />
            <p class="mt-2 text-xs text-slate-200">风险位置已定位，影像底图暂未就绪</p>
            <p class="mt-1 text-[10px] text-slate-500">可返回真实地图查看空间位置</p>
          </div>
        </div>

        <div class="absolute left-3 top-3 z-10 flex items-center gap-1 rounded-xl border border-white/10 bg-[#07111f]/85 p-1 shadow-xl backdrop-blur">
          <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-35" title="放大" :disabled="zoom >= 4" @click="zoomIn"><SafeIcon name="Plus" :size="14" /></button>
          <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-35" title="缩小" :disabled="zoom <= 1" @click="zoomOut"><SafeIcon name="Minus" :size="14" /></button>
          <span class="min-w-10 px-1 text-center text-[10px] font-semibold text-cyan-200">{{ zoom.toFixed(1) }}×</span>
          <span class="h-5 w-px bg-white/10" />
          <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-35" title="定位选中风险" :disabled="!selectedOverlay" @click="focusSelected"><SafeIcon name="ScanSearch" :size="14" /></button>
          <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-slate-300 transition hover:bg-white/10 hover:text-white" title="复位视图" @click="resetView"><SafeIcon name="Maximize2" :size="14" /></button>
        </div>

        <button
          v-if="selectedLocation"
          type="button"
          class="absolute bottom-4 right-4 z-10 flex items-center gap-2 rounded-xl border border-cyan-300/20 bg-[#07111f]/88 px-3 py-2 text-left shadow-xl backdrop-blur transition hover:border-cyan-300/40"
          title="复制选中风险坐标"
          @click="copySelectedCoordinate"
        >
          <span class="grid h-7 w-7 place-items-center rounded-lg bg-cyan-300/10 text-cyan-200"><SafeIcon name="MapPin" :size="14" /></span>
          <span><span class="block text-[9px] text-slate-400">选中风险坐标</span><strong class="mt-0.5 block font-mono text-[11px] text-cyan-100">{{ formatGeographicCoordinate(selectedLocation) }}</strong></span>
          <SafeIcon name="Copy" :size="12" class="text-slate-500" />
        </button>

        <div v-if="cursorLocation" class="pointer-events-none absolute right-3 top-3 z-10 rounded-lg border border-white/10 bg-[#07111f]/75 px-2.5 py-1.5 font-mono text-[9px] text-slate-300 backdrop-blur">
          光标 {{ cursorLocation.longitude.toFixed(6) }}, {{ cursorLocation.latitude.toFixed(6) }}
        </div>

        <div
          v-if="ortho?.projectionWarning"
          class="absolute top-3 right-3 max-w-[320px] rounded-[--radius] border border-[hsl(var(--warning))]/30 bg-background/90 px-3 py-2 text-xs text-[hsl(var(--warning))] shadow-sm backdrop-blur"
        >
          {{ ortho.projectionWarning }}
        </div>
      </template>

      <template v-else>
        <div class="absolute inset-0">
          <svg class="h-full w-full" viewBox="0 0 1000 620" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" aria-label="正射影像场景示意">
            <defs>
              <pattern id="fallback-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#9fe8ef" stroke-opacity=".08" stroke-width="0.6" />
              </pattern>
              <linearGradient id="fallback-land" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#17362f" />
                <stop offset=".55" stop-color="#274a38" />
                <stop offset="1" stop-color="#172d29" />
              </linearGradient>
              <linearGradient id="fallback-water" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#19506b" />
                <stop offset=".5" stop-color="#246f84" />
                <stop offset="1" stop-color="#123c57" />
              </linearGradient>
              <filter id="fallback-shadow">
                <feDropShadow dx="0" dy="3" stdDeviation="8" flood-color="#02070c" flood-opacity=".55" />
              </filter>
            </defs>
            <rect width="1000" height="620" fill="url(#fallback-land)" />
            <path d="M-80 98 C155 42 258 198 420 183 C590 168 681 35 1080 94 L1080 284 C792 221 667 349 477 338 C281 326 151 203 -80 286Z" fill="url(#fallback-water)" filter="url(#fallback-shadow)" />
            <path d="M-80 303 C160 216 280 363 466 367 C672 372 779 255 1080 319" fill="none" stroke="#8adce3" stroke-opacity=".28" stroke-width="6" stroke-dasharray="12 10" />
            <path d="M84 468 L412 390 L521 474 L221 570Z" fill="#947452" fill-opacity=".35" />
            <path d="M585 394 L936 438" stroke="#c8b27b" stroke-opacity=".3" stroke-width="24" />
            <path d="M585 394 L936 438" stroke="#182b27" stroke-opacity=".75" stroke-width="11" stroke-dasharray="24 13" />
            <rect width="1000" height="620" fill="url(#fallback-grid)" />
          </svg>
        </div>

        <div class="absolute inset-0 flex items-center justify-center">
          <div class="relative w-full h-full">
            <div
              v-for="risk in risksByLevel.high"
              :key="`high-${risk?.id}`"
              class="absolute w-3 h-3 rounded-full bg-destructive cursor-pointer transform -translate-x-1/2 -translate-y-1/2 hover:scale-150 transition-transform shadow-lg shadow-destructive/50"
              :style="{
                left: `${20 + ((risk?.score || 0) % 60)}%`,
                top: `${30 + ((risk?.score || 0) % 40)}%`,
              }"
              :class="selectedRiskId === risk?.id && 'ring-2 ring-destructive ring-offset-2 ring-offset-background scale-150'"
              :title="`${risk?.title} (${risk?.score}分)`"
              @click="handleRiskClick(risk?.id || '')"
              @pointerenter="emit('risk-hover', risk?.id || null)"
              @pointerleave="emit('risk-hover', null)"
            />

            <div
              v-for="risk in risksByLevel.medium"
              :key="`medium-${risk?.id}`"
              class="absolute w-2.5 h-2.5 rounded-full bg-[hsl(var(--warning))] cursor-pointer transform -translate-x-1/2 -translate-y-1/2 hover:scale-150 transition-transform shadow-lg shadow-[hsl(var(--warning) / 0.5)]"
              :style="{
                left: `${35 + ((risk?.score || 0) % 50)}%`,
                top: `${45 + ((risk?.score || 0) % 35)}%`,
              }"
              :class="selectedRiskId === risk?.id && 'ring-2 ring-[hsl(var(--warning))] ring-offset-2 ring-offset-background scale-150'"
              :title="`${risk?.title} (${risk?.score}分)`"
              @click="handleRiskClick(risk?.id || '')"
              @pointerenter="emit('risk-hover', risk?.id || null)"
              @pointerleave="emit('risk-hover', null)"
            />

            <div
              v-for="risk in risksByLevel.low"
              :key="`low-${risk?.id}`"
              class="absolute w-2 h-2 rounded-full bg-[hsl(var(--success))] cursor-pointer transform -translate-x-1/2 -translate-y-1/2 hover:scale-150 transition-transform shadow-lg shadow-[hsl(var(--success) / 0.5)]"
              :style="{
                left: `${50 + ((risk?.score || 0) % 40)}%`,
                top: `${60 + ((risk?.score || 0) % 30)}%`,
              }"
              :class="selectedRiskId === risk?.id && 'ring-2 ring-[hsl(var(--success))] ring-offset-2 ring-offset-background scale-150'"
              :title="`${risk?.title} (${risk?.score}分)`"
              @click="handleRiskClick(risk?.id || '')"
              @pointerenter="emit('risk-hover', risk?.id || null)"
              @pointerleave="emit('risk-hover', null)"
            />

            <div
              v-for="risk in risksByLevel.review_required"
              :key="`review-${risk?.id}`"
              class="absolute w-2.5 h-2.5 rounded-full bg-accent cursor-pointer transform -translate-x-1/2 -translate-y-1/2 hover:scale-150 transition-transform shadow-lg shadow-accent/50 animate-pulse"
              :style="{
                left: `${65 + ((risk?.score || 0) % 30)}%`,
                top: `${50 + ((risk?.score || 0) % 35)}%`,
              }"
              :class="selectedRiskId === risk?.id && 'ring-2 ring-accent ring-offset-2 ring-offset-background scale-150'"
              :title="`${risk?.title} (待复核)`"
              @click="handleRiskClick(risk?.id || '')"
              @pointerenter="emit('risk-hover', risk?.id || null)"
              @pointerleave="emit('risk-hover', null)"
            />
          </div>
        </div>
        <div class="pointer-events-none absolute inset-x-0 top-1/3 h-px bg-cyan-300/40 shadow-[0_0_18px_rgba(103,232,249,.55)] animate-pulse" />
        <div class="absolute right-4 top-4 rounded-lg border border-white/10 bg-[#07111f]/75 px-3 py-2 text-[10px] text-slate-300 backdrop-blur">
          场景基准影像 · 空间基准已锁定
        </div>
      </template>

      <div class="absolute bottom-4 left-4 surface-base card-padding space-y-2 text-xs">
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full bg-destructive" />
          <span class="text-foreground">高风险</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full bg-[hsl(var(--warning))]" />
          <span class="text-foreground">中风险</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full bg-[hsl(var(--success))]" />
          <span class="text-foreground">低风险</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full bg-accent animate-pulse" />
          <span class="text-foreground">待复核</span>
        </div>
      </div>

      <div v-if="risks.length === 0 && !loading" class="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div class="text-center text-muted-foreground">
          <SafeIcon name="MapPin" :size="48" class="mx-auto mb-2 opacity-20" />
          <p class="text-sm">暂无风险数据</p>
        </div>
      </div>
    </div>

    <div class="flex-shrink-0 border-t border-border/50 bg-background/50 backdrop-blur-sm p-2 flex items-center justify-between gap-3">
      <div class="min-w-0 text-xs text-muted-foreground truncate">
        {{ hasAgentVisualization ? '正射图空间研判' : '场景风险标注' }} · {{ currentZoneName }} · {{ risks.length }} 个风险<span v-if="spatial?.primary"> · EPSG:{{ spatial.primary.epsg }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import GeoRasterImage from '@/components/common/GeoRasterImage.vue'
import WebglPointCloudViewer from '@/components/common/WebglPointCloudViewer.vue'
import type { AgentArtifactView, AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

type ResultView = 'pointcloud' | 'change' | 'ortho' | 'geometry'

const props = defineProps<{ snapshot: AgentPresentationSnapshot }>()
const activeView = ref<ResultView>('change')
const splitPercent = ref(52)
const maskOpacity = ref(48)
const showMask = ref(true)
const imageZoom = ref(1)

function artifact(role: string): AgentArtifactView | undefined {
  return props.snapshot.evidence.artifacts.find((item) => item.role === role && (item.downloadUrl || item.previewUrl))
}

function displayUrl(value?: AgentArtifactView) {
  return value?.previewUrl || value?.downloadUrl
}

function displayMediaType(value?: AgentArtifactView) {
  return value?.previewUrl && value.previewUrl !== value.downloadUrl ? 'image/webp' : value?.mediaType
}

const language = computed(() => props.snapshot.evidence.languageResult)
const semantic = computed(() => props.snapshot.evidence.semanticResult)
const geometry = computed(() => props.snapshot.evidence.geometryResult)
const pointCloud = computed(() => artifact('point_cloud_path'))
const pointPreview = computed(() => artifact('point_visualization'))
const targetMask = computed(() => artifact('target_mask'))
const probabilities = computed(() => artifact('target_probabilities'))
const semanticLabels = computed(() => artifact('point_labels'))
const relationMask = computed(() => artifact('relation_mask'))
const beforeImage = computed(() => artifact('before_image_path'))
const afterImage = computed(() => artifact('after_image_path'))
const taskImage = computed(() => artifact('image_path'))
const orthoImage = computed(() => afterImage.value || taskImage.value || beforeImage.value)
const changeMask = computed(() => artifact('change_mask'))
const changeProbability = computed(() => artifact('change_probability_map'))
const changeReport = computed(() => artifact('change_regions'))
const regions = computed(() => props.snapshot.evidence.regions)
const primary = computed(() => props.snapshot.spatial?.primary)
const qualityLabel = computed(() => ({ passed: '质量验证通过', limited: '结果存在限制', review_required: '建议人工复核', unavailable: '等待质量结果' }[props.snapshot.quality.verdict]))

const views = computed<Array<{ id: ResultView; label: string; icon: string; summary: string }>>(() => [
  ...(beforeImage.value && afterImage.value && (changeMask.value || changeProbability.value || changeReport.value) ? [{ id: 'change' as const, label: '变化检测', icon: 'Columns2', summary: '前后时相与变化区域联合核验' }] : []),
  ...(orthoImage.value ? [{ id: 'ortho' as const, label: '正射影像', icon: 'Map', summary: '真实空间影像与候选区域定位' }] : []),
  ...(pointCloud.value ? [{ id: 'pointcloud' as const, label: '三维点云', icon: 'Box', summary: '点级识别、语义分类与置信度证据' }] : []),
  ...(geometry.value && pointCloud.value ? [{ id: 'geometry' as const, label: '几何关系', icon: 'Orbit', summary: '关系掩膜、空间范围与测量结果' }] : []),
])

const activeDefinition = computed(() => views.value.find((item) => item.id === activeView.value) || views.value[0])
const rasterWidth = computed(() => primary.value?.raster?.width || 1)
const rasterHeight = computed(() => primary.value?.raster?.height || 1)

watch(views, (next) => {
  if (!next.some((item) => item.id === activeView.value)) activeView.value = next[0]?.id || 'pointcloud'
}, { immediate: true })

function percent(value?: number, digits = 1) {
  return value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`
}

function zoomBy(delta: number) {
  imageZoom.value = Math.min(3, Math.max(1, imageZoom.value + delta))
}
</script>

<template>
  <section v-if="views.length" class="overflow-hidden rounded-3xl border border-cyan-300/15 bg-[#06101c] shadow-[0_28px_90px_rgba(0,0,0,.32)]">
    <header class="flex flex-col gap-4 border-b border-white/[0.07] bg-gradient-to-r from-cyan-400/[0.08] via-transparent to-violet-400/[0.06] px-5 py-4 xl:flex-row xl:items-center xl:justify-between">
      <div class="flex items-start gap-3"><span class="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200"><SafeIcon name="ScanSearch" :size="21" /></span><div><div class="flex flex-wrap items-center gap-2"><h2 class="text-base font-semibold text-white">Agent 多模态结果画布</h2><span class="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2.5 py-1 text-[9px] font-semibold text-emerald-200">{{ views.length }} 类真实视图已对齐</span></div><p class="mt-1 max-w-3xl text-[11px] leading-5 text-slate-400">视图由本次后端实际规划和产物动态生成；多个专家结果分别保留，可切换核验而不会互相覆盖。</p></div></div>
      <nav class="flex flex-wrap items-center gap-1 rounded-xl border border-white/10 bg-black/20 p-1">
        <button v-for="view in views" :key="view.id" type="button" class="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[10px] transition" :class="activeView === view.id ? 'bg-cyan-300/15 text-cyan-100 shadow-inner' : 'text-slate-400 hover:bg-white/5 hover:text-white'" @click="activeView = view.id; imageZoom = 1"><SafeIcon :name="view.icon" :size="13" />{{ view.label }}</button>
      </nav>
    </header>

    <div class="grid min-h-[650px] xl:grid-cols-[minmax(0,1fr)_340px]">
      <div class="relative min-h-[570px] overflow-hidden border-b border-white/[0.07] xl:border-b-0 xl:border-r">
        <WebglPointCloudViewer
          v-if="activeView === 'pointcloud' && pointCloud?.downloadUrl"
          :source-url="pointCloud.downloadUrl"
          :preview-url="pointPreview?.downloadUrl"
          :target-mask-url="targetMask?.downloadUrl"
          :target-probabilities-url="probabilities?.downloadUrl"
          :semantic-labels-url="semanticLabels?.downloadUrl"
          :semantic-classes="semantic?.classes"
          :selected-points="language?.selectedPoints"
          :selected-ratio="language?.selectedRatio"
          :execution-confidence="language?.executionConfidence"
          :applied-threshold="language?.appliedThreshold"
          title="场景三维证据 · 点级结果"
        />

        <div v-else-if="activeView === 'change'" class="absolute inset-0 overflow-hidden bg-[#030a12]">
          <div class="absolute inset-0 transition-transform duration-300" :style="{ transform: `scale(${imageZoom})` }">
            <GeoRasterImage :url="displayUrl(beforeImage)" :media-type="displayMediaType(beforeImage)" alt="巡查前时相影像" />
            <div class="absolute inset-0" :style="{ clipPath: `inset(0 0 0 ${splitPercent}%)` }"><GeoRasterImage :url="displayUrl(afterImage)" :media-type="displayMediaType(afterImage)" alt="巡查后时相影像" /></div>
            <GeoRasterImage v-if="showMask && displayUrl(changeMask)" :url="displayUrl(changeMask)" :media-type="displayMediaType(changeMask)" alt="变化检测掩膜" class="absolute inset-0 mix-blend-screen" :style="{ opacity: maskOpacity / 100 }" />
          </div>
          <div class="absolute inset-y-0 w-px bg-cyan-200 shadow-[0_0_18px_#67e8f9]" :style="{ left: `${splitPercent}%` }"><span class="absolute left-1/2 top-1/2 grid h-9 w-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-cyan-100/50 bg-[#07111f]/90 text-cyan-100"><SafeIcon name="MoveHorizontal" :size="15" /></span></div>
          <span class="absolute left-4 top-4 rounded-lg border border-white/10 bg-black/60 px-3 py-1.5 text-[10px] text-white backdrop-blur">巡查前时相</span><span class="absolute right-4 top-4 rounded-lg border border-orange-300/20 bg-black/60 px-3 py-1.5 text-[10px] text-orange-100 backdrop-blur">巡查后时相</span>
          <div class="absolute bottom-5 left-1/2 flex w-[min(92%,520px)] -translate-x-1/2 items-center gap-3 rounded-xl border border-white/10 bg-black/65 px-4 py-2 backdrop-blur"><SafeIcon name="Columns2" :size="13" class="text-cyan-200" /><input v-model.number="splitPercent" type="range" min="5" max="95" class="min-w-0 flex-1 accent-cyan-300" aria-label="前后时相分割位置"><span class="w-9 font-mono text-[9px] text-cyan-100">{{ splitPercent }}%</span><template v-if="changeMask"><button type="button" class="rounded-lg px-2 py-1 text-[9px]" :class="showMask ? 'bg-rose-300/15 text-rose-100' : 'text-slate-500'" @click="showMask = !showMask">变化层</button><input v-if="showMask" v-model.number="maskOpacity" type="range" min="10" max="85" class="w-20 accent-rose-400" aria-label="变化层透明度"></template></div>
        </div>

        <div v-else-if="activeView === 'ortho'" class="absolute inset-0 overflow-hidden bg-[#030a12]">
          <div class="absolute inset-0 transition-transform duration-300" :style="{ transform: `scale(${imageZoom})` }"><GeoRasterImage :url="displayUrl(orthoImage)" :media-type="displayMediaType(orthoImage)" :alt="orthoImage?.title" /><svg v-if="regions.length" class="pointer-events-none absolute inset-0 h-full w-full object-contain" :viewBox="`0 0 ${rasterWidth} ${rasterHeight}`" preserveAspectRatio="xMidYMid meet"><g v-for="region in regions" :key="region.regionId"><rect v-if="region.bboxPixel" :x="region.bboxPixel.x" :y="region.bboxPixel.y" :width="region.bboxPixel.width" :height="region.bboxPixel.height" fill="rgba(251,146,60,.12)" stroke="#fb923c" :stroke-width="Math.max(rasterWidth / 600, 2)" /><polygon v-if="region.polygonPixel" :points="region.polygonPixel.map((point) => `${point.x},${point.y}`).join(' ')" fill="rgba(244,63,94,.16)" stroke="#fb7185" :stroke-width="Math.max(rasterWidth / 600, 2)" /></g></svg></div>
          <div class="absolute right-4 top-4 flex items-center gap-1 rounded-xl border border-white/10 bg-black/60 p-1 backdrop-blur"><button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-slate-300 hover:bg-white/10" @click="zoomBy(-0.25)"><SafeIcon name="ZoomOut" :size="14" /></button><span class="w-10 text-center font-mono text-[9px] text-cyan-100">{{ Math.round(imageZoom * 100) }}%</span><button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-slate-300 hover:bg-white/10" @click="zoomBy(0.25)"><SafeIcon name="ZoomIn" :size="14" /></button><button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-slate-300 hover:bg-white/10" @click="imageZoom = 1"><SafeIcon name="RotateCcw" :size="13" /></button></div>
          <div class="absolute bottom-4 left-4 rounded-xl border border-white/10 bg-black/60 px-3 py-2 text-[10px] text-slate-300 backdrop-blur"><span class="text-cyan-200">{{ orthoImage?.title }}</span><span v-if="primary?.epsg" class="ml-3 text-slate-500">EPSG:{{ primary.epsg }}</span></div>
        </div>

        <WebglPointCloudViewer
          v-else-if="activeView === 'geometry' && pointCloud?.downloadUrl"
          :source-url="pointCloud.downloadUrl"
          :target-mask-url="relationMask?.downloadUrl"
          target-mask-array-name="relation_mask"
          :selected-points="geometry?.selectedPoints"
          :selected-ratio="geometry?.selectedTargetRatio"
          title="空间关系命中区域 · 三维几何证据"
        />
      </div>

      <aside class="flex flex-col bg-[#081522]">
        <div class="border-b border-white/[0.07] p-5"><p class="text-[9px] font-semibold tracking-[0.18em] text-cyan-300">ACTIVE EVIDENCE VIEW</p><h3 class="mt-2 text-sm font-semibold text-white">{{ activeDefinition?.label }}</h3><p class="mt-1 text-[11px] leading-5 text-slate-400">{{ activeDefinition?.summary }}</p><div class="mt-3 flex flex-wrap gap-1.5"><span class="rounded-lg border border-white/10 bg-black/20 px-2.5 py-1.5 text-[9px] text-slate-300">EPSG:{{ primary?.epsg || '—' }}</span><span class="rounded-lg border border-emerald-300/15 bg-emerald-300/10 px-2.5 py-1.5 text-[9px] text-emerald-200">{{ qualityLabel }}</span></div></div>

        <div v-if="activeView === 'pointcloud'" class="space-y-4 p-5"><div class="grid grid-cols-2 gap-2"><div class="rounded-xl border border-orange-300/15 bg-orange-300/[0.06] p-3"><p class="text-[9px] text-slate-500">目标点数</p><strong class="mt-1 block text-base text-orange-200">{{ language?.selectedPoints?.toLocaleString('zh-CN') || '—' }}</strong></div><div class="rounded-xl border border-orange-300/15 bg-orange-300/[0.06] p-3"><p class="text-[9px] text-slate-500">目标占比</p><strong class="mt-1 block text-base text-orange-200">{{ percent(language?.selectedRatio, 2) }}</strong></div></div><div v-if="semantic" class="rounded-xl border border-cyan-300/15 bg-cyan-300/[0.05] p-3"><p class="text-[10px] text-cyan-200">{{ semantic.modeLabel }}</p><p class="mt-2 text-[10px] leading-5 text-slate-400">识别 {{ semantic.numPresentClasses ?? '—' }} 类地物，分析 {{ semantic.numPoints?.toLocaleString('zh-CN') || '—' }} 个源点。</p></div><p class="rounded-xl border border-amber-300/15 bg-amber-300/[0.05] p-3 text-[10px] leading-5 text-amber-100">点云画布保留源点空间结构，高亮结果是模型证据，不直接等同于业务风险。</p></div>

        <div v-else-if="activeView === 'change'" class="space-y-4 p-5"><div class="grid grid-cols-2 gap-2"><div class="rounded-xl border border-rose-300/15 bg-rose-300/[0.05] p-3"><p class="text-[9px] text-slate-500">变化区域</p><strong class="mt-1 block text-base text-rose-200">{{ regions.length }} 处</strong></div><div class="rounded-xl border border-cyan-300/15 bg-cyan-300/[0.05] p-3"><p class="text-[9px] text-slate-500">变化产物</p><strong class="mt-1 block text-base text-cyan-200">{{ [changeMask, changeProbability].filter(Boolean).length }} 项</strong></div></div><div class="space-y-2"><article v-for="region in regions.slice(0, 6)" :key="region.regionId" class="rounded-xl border border-white/[0.07] bg-black/15 p-3"><div class="flex items-center justify-between gap-2"><span class="text-[10px] font-medium text-white">{{ region.label }}</span><span class="text-[9px] text-orange-200">{{ percent(region.score) }}</span></div><p class="mt-1 text-[9px] leading-4 text-slate-500">{{ region.summary }}</p></article><p v-if="!regions.length" class="text-[10px] leading-5 text-slate-500">两期影像和变化层已经归档，后端未返回独立变化区域。</p></div></div>

        <div v-else-if="activeView === 'ortho'" class="space-y-4 p-5"><div class="rounded-xl border border-cyan-300/15 bg-cyan-300/[0.05] p-3"><p class="text-[9px] text-slate-500">影像尺寸</p><strong class="mt-1 block text-sm text-cyan-100">{{ primary?.raster ? `${primary.raster.width.toLocaleString('zh-CN')} × ${primary.raster.height.toLocaleString('zh-CN')}` : '读取空间元数据' }}</strong></div><div v-if="primary?.geographicBounds" class="rounded-xl border border-white/[0.07] bg-black/15 p-3"><p class="text-[10px] text-white">地理覆盖范围</p><div class="mt-2 grid grid-cols-2 gap-2 font-mono text-[9px] text-slate-400"><span>W {{ primary.geographicBounds.west.toFixed(6) }}</span><span>E {{ primary.geographicBounds.east.toFixed(6) }}</span><span>S {{ primary.geographicBounds.south.toFixed(6) }}</span><span>N {{ primary.geographicBounds.north.toFixed(6) }}</span></div></div><p class="rounded-xl border border-white/[0.07] bg-black/15 p-3 text-[10px] leading-5 text-slate-400">GeoTIFF 会在浏览器中按画布尺寸读取，保留原始空间元数据，同时避免把整幅超高分辨率影像解码到显存。</p></div>

        <div v-else class="space-y-4 p-5"><div class="rounded-xl border border-violet-300/15 bg-violet-300/[0.05] p-3"><p class="text-[9px] text-slate-500">空间操作</p><strong class="mt-1 block text-sm text-violet-100">{{ geometry?.operationLabel }}</strong><p class="mt-1 text-[9px] text-slate-500">{{ geometry?.targetClassName }}<template v-if="geometry?.referenceClassName"> 相对 {{ geometry.referenceClassName }}</template></p></div><div class="grid grid-cols-2 gap-2"><div class="rounded-xl border border-white/[0.07] bg-black/15 p-3"><p class="text-[9px] text-slate-500">命中点数</p><strong class="mt-1 block text-sm text-white">{{ geometry?.selectedPoints?.toLocaleString('zh-CN') || '—' }}</strong></div><div class="rounded-xl border border-white/[0.07] bg-black/15 p-3"><p class="text-[9px] text-slate-500">目标比例</p><strong class="mt-1 block text-sm text-white">{{ percent(geometry?.selectedTargetRatio) }}</strong></div></div><div class="space-y-2"><div v-for="item in geometry?.measurements || []" :key="item.label" class="flex items-center justify-between rounded-lg border border-white/[0.07] bg-black/15 px-3 py-2 text-[10px]"><span class="text-slate-400">{{ item.label }}</span><span class="text-violet-200">{{ item.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }} {{ item.unit }}</span></div></div><p v-if="!relationMask" class="rounded-xl border border-amber-300/15 bg-amber-300/[0.05] p-3 text-[10px] leading-5 text-amber-100">几何报告已可视化；本次后端没有提供逐点关系掩膜，因此三维画布仅显示原始场景。</p></div>

        <div class="mt-auto border-t border-white/[0.07] p-5"><div class="flex items-center justify-between text-[10px]"><span class="text-slate-500">本次可视化视图</span><span class="font-semibold text-cyan-200">{{ views.length }} 类</span></div><div class="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.07]"><div class="h-full rounded-full bg-gradient-to-r from-cyan-400 via-violet-400 to-orange-400" style="width:100%" /></div></div>
      </aside>
    </div>
  </section>
</template>

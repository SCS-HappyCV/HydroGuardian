<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { loadLasPointCloud, type LasHeader } from '@/lib/las-point-cloud'
import { loadNpzArray, loadPointVisualizationPreview } from '@/lib/numpy-archive'

const props = withDefaults(defineProps<{
  sourceUrl?: string
  previewUrl?: string
  targetMaskUrl?: string
  targetMaskArrayName?: string
  targetProbabilitiesUrl?: string
  semanticLabelsUrl?: string
  semanticClasses?: Array<{ classId: number; className: string; pointCount: number; pointRatio: number }>
  title?: string
  pointBudget?: number
  selectedPoints?: number
  selectedRatio?: number
  executionConfidence?: number
  appliedThreshold?: number
  focusProjected?: { x: number; y: number; key?: string }
  focusLabel?: string
}>(), {
  title: '三维点云场景',
  pointBudget: 240000,
  appliedThreshold: 0.3,
  targetMaskArrayName: 'target_mask',
})

type ColorMode = 'source' | 'height' | 'mask' | 'confidence' | 'semantic'

const canvas = ref<HTMLCanvasElement | null>(null)
const loading = ref(false)
const progress = ref(0)
const error = ref('')
const header = ref<LasHeader | null>(null)
const renderedPointCount = ref(0)
const colorMode = ref<ColorMode>('source')
const pointSize = ref(2)
const targetOnly = ref(false)
const resultAvailable = ref(false)
const semanticAvailable = ref(false)
const resultError = ref('')
const thresholdValue = ref(props.appliedThreshold)
const yaw = ref(-0.7)
const pitch = ref(-0.72)
const distance = ref(3.1)
const focusX = ref(0)
const focusZ = ref(0)

let gl: WebGLRenderingContext | null = null
let program: WebGLProgram | null = null
let positionBuffer: WebGLBuffer | null = null
let colorBuffer: WebGLBuffer | null = null
let targetBuffer: WebGLBuffer | null = null
let probabilityBuffer: WebGLBuffer | null = null
let animationFrame = 0
let resizeObserver: ResizeObserver | null = null
let abortController: AbortController | null = null
let dragging = false
let pointerX = 0
let pointerY = 0

const totalPointLabel = computed(() => header.value?.pointCount.toLocaleString('zh-CN') || '—')
const renderedPointLabel = computed(() => renderedPointCount.value.toLocaleString('zh-CN'))
const elevationLabel = computed(() => header.value ? `${header.value.bounds.minZ.toFixed(1)}–${header.value.bounds.maxZ.toFixed(1)} m` : '—')
const resultModes = computed(() => [
  { id: 'source', label: '原始色彩' },
  { id: 'height', label: '高程着色' },
  ...(semanticAvailable.value ? [{ id: 'semantic', label: '语义分类' }] : []),
  ...(resultAvailable.value ? [{ id: 'mask', label: '目标掩膜' }, { id: 'confidence', label: '置信热力' }] : []),
])
const selectedRatioLabel = computed(() => props.selectedRatio === undefined ? '—' : `${(props.selectedRatio * 100).toFixed(2)}%`)
const confidenceLabel = computed(() => props.executionConfidence === undefined ? '—' : `${(props.executionConfidence * 100).toFixed(1)}%`)
const semanticPalette = ['#22d3ee', '#a78bfa', '#f59e0b', '#fb7185', '#34d399', '#f97316', '#60a5fa', '#84cc16', '#eab308', '#14b8a6', '#10b981', '#c084fc', '#38bdf8', '#f43f5e', '#94a3b8']

function shader(type: number, source: string): WebGLShader {
  if (!gl) throw new Error('WebGL 尚未初始化')
  const item = gl.createShader(type)
  if (!item) throw new Error('无法创建 WebGL 着色器')
  gl.shaderSource(item, source)
  gl.compileShader(item)
  if (!gl.getShaderParameter(item, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(item) || '着色器编译失败')
  return item
}

function initializeRenderer() {
  if (!canvas.value) return
  gl = canvas.value.getContext('webgl', { antialias: true, alpha: true, powerPreference: 'high-performance' })
  if (!gl) {
    error.value = '当前设备未启用 WebGL，无法显示点云'
    return
  }
  const vertex = shader(gl.VERTEX_SHADER, `
    attribute vec3 aPosition;
    attribute vec3 aColor;
    attribute float aTarget;
    attribute float aProbability;
    uniform float uYaw;
    uniform float uPitch;
    uniform float uDistance;
    uniform float uAspect;
    uniform float uPointSize;
    uniform float uFocusX;
    uniform float uFocusZ;
    varying vec3 vColor;
    varying float vHeight;
    varying float vTarget;
    varying float vProbability;
    void main() {
      float cy = cos(uYaw), sy = sin(uYaw);
      float cp = cos(uPitch), sp = sin(uPitch);
      vec3 centered = aPosition - vec3(uFocusX, 0.0, uFocusZ);
      vec3 yawed = vec3(cy * centered.x - sy * centered.z, centered.y, sy * centered.x + cy * centered.z);
      vec3 rotated = vec3(yawed.x, cp * yawed.y - sp * yawed.z, sp * yawed.y + cp * yawed.z);
      float depth = max(0.18, uDistance - rotated.z);
      float focal = 2.41421356;
      float nearPlane = 0.1;
      float farPlane = 20.0;
      gl_Position = vec4(rotated.x * focal / uAspect, rotated.y * focal, ((farPlane + nearPlane) / (farPlane - nearPlane)) * depth - (2.0 * farPlane * nearPlane / (farPlane - nearPlane)), depth);
      gl_PointSize = uPointSize * clamp(3.2 / depth, 0.65, 2.4);
      vColor = aColor;
      vHeight = clamp(aPosition.y * 0.5 + 0.5, 0.0, 1.0);
      vTarget = aTarget;
      vProbability = aProbability;
    }
  `)
  const fragment = shader(gl.FRAGMENT_SHADER, `
    precision mediump float;
    uniform float uColorMode;
    uniform float uTargetOnly;
    uniform float uThreshold;
    varying vec3 vColor;
    varying float vHeight;
    varying float vTarget;
    varying float vProbability;
    vec3 heightColor(float value) {
      if (value < 0.45) return mix(vec3(0.05, 0.55, 0.85), vec3(0.18, 0.88, 0.70), value / 0.45);
      return mix(vec3(0.18, 0.88, 0.70), vec3(1.0, 0.54, 0.22), (value - 0.45) / 0.55);
    }
    vec3 confidenceColor(float value) {
      float t = clamp(value / 0.55, 0.0, 1.0);
      if (t < 0.34) return mix(vec3(0.08, 0.28, 0.72), vec3(0.05, 0.82, 0.88), t / 0.34);
      if (t < 0.68) return mix(vec3(0.05, 0.82, 0.88), vec3(1.0, 0.80, 0.22), (t - 0.34) / 0.34);
      return mix(vec3(1.0, 0.80, 0.22), vec3(1.0, 0.24, 0.18), (t - 0.68) / 0.32);
    }
    vec3 semanticColor(float label) {
      if (label < 1.5) return vec3(0.13, 0.83, 0.93);
      if (label < 2.5) return vec3(0.65, 0.55, 0.98);
      if (label < 3.5) return vec3(0.96, 0.62, 0.04);
      if (label < 4.5) return vec3(0.98, 0.44, 0.58);
      if (label < 5.5) return vec3(0.20, 0.83, 0.60);
      if (label < 6.5) return vec3(0.98, 0.45, 0.09);
      if (label < 7.5) return vec3(0.38, 0.65, 0.98);
      if (label < 8.5) return vec3(0.52, 0.80, 0.09);
      if (label < 9.5) return vec3(0.92, 0.70, 0.03);
      if (label < 10.5) return vec3(0.08, 0.72, 0.65);
      if (label < 11.5) return vec3(0.06, 0.73, 0.51);
      if (label < 12.5) return vec3(0.75, 0.52, 0.98);
      if (label < 13.5) return vec3(0.22, 0.74, 0.97);
      if (label < 14.5) return vec3(0.96, 0.24, 0.36);
      return vec3(0.58, 0.64, 0.72);
    }
    void main() {
      vec2 center = gl_PointCoord - vec2(0.5);
      if (dot(center, center) > 0.25) discard;
      bool selected = vTarget > 0.5 || vProbability >= uThreshold;
      if (uTargetOnly > 0.5 && uColorMode < 3.5 && !selected) discard;
      vec3 color = vColor;
      float alpha = 0.94;
      if (uColorMode > 3.5) color = semanticColor(vTarget);
      else if (uColorMode > 2.5) color = confidenceColor(vProbability);
      else if (uColorMode > 1.5) {
        color = selected ? vec3(1.0, 0.32, 0.20) : vec3(0.10, 0.19, 0.25);
        alpha = selected ? 0.98 : 0.16;
      } else if (uColorMode > 0.5) color = heightColor(vHeight);
      gl_FragColor = vec4(color, alpha);
    }
  `)
  program = gl.createProgram()
  if (!program) throw new Error('无法创建 WebGL 程序')
  gl.attachShader(program, vertex)
  gl.attachShader(program, fragment)
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'WebGL 程序链接失败')
  gl.deleteShader(vertex)
  gl.deleteShader(fragment)
  positionBuffer = gl.createBuffer()
  colorBuffer = gl.createBuffer()
  targetBuffer = gl.createBuffer()
  probabilityBuffer = gl.createBuffer()
  resizeObserver = new ResizeObserver(resizeCanvas)
  resizeObserver.observe(canvas.value)
  render()
}

function resizeCanvas() {
  if (!canvas.value || !gl) return
  const ratio = Math.min(2, window.devicePixelRatio || 1)
  const width = Math.max(1, Math.round(canvas.value.clientWidth * ratio))
  const height = Math.max(1, Math.round(canvas.value.clientHeight * ratio))
  if (canvas.value.width !== width || canvas.value.height !== height) {
    canvas.value.width = width
    canvas.value.height = height
    gl.viewport(0, 0, width, height)
  }
}

function render() {
  if (!gl || !program || !canvas.value) return
  resizeCanvas()
  gl.clearColor(0.018, 0.047, 0.086, 1)
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT)
  gl.enable(gl.DEPTH_TEST)
  gl.enable(gl.BLEND)
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
  gl.useProgram(program)
  const positionLocation = gl.getAttribLocation(program, 'aPosition')
  const colorLocation = gl.getAttribLocation(program, 'aColor')
  const targetLocation = gl.getAttribLocation(program, 'aTarget')
  const probabilityLocation = gl.getAttribLocation(program, 'aProbability')
  if (positionBuffer) {
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
    gl.enableVertexAttribArray(positionLocation)
    gl.vertexAttribPointer(positionLocation, 3, gl.FLOAT, false, 0, 0)
  }
  if (colorBuffer) {
    gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer)
    gl.enableVertexAttribArray(colorLocation)
    gl.vertexAttribPointer(colorLocation, 3, gl.FLOAT, false, 0, 0)
  }
  if (targetBuffer) {
    gl.bindBuffer(gl.ARRAY_BUFFER, targetBuffer)
    gl.enableVertexAttribArray(targetLocation)
    gl.vertexAttribPointer(targetLocation, 1, gl.FLOAT, false, 0, 0)
  }
  if (probabilityBuffer) {
    gl.bindBuffer(gl.ARRAY_BUFFER, probabilityBuffer)
    gl.enableVertexAttribArray(probabilityLocation)
    gl.vertexAttribPointer(probabilityLocation, 1, gl.FLOAT, false, 0, 0)
  }
  gl.uniform1f(gl.getUniformLocation(program, 'uYaw'), yaw.value)
  gl.uniform1f(gl.getUniformLocation(program, 'uPitch'), pitch.value)
  gl.uniform1f(gl.getUniformLocation(program, 'uDistance'), distance.value)
  gl.uniform1f(gl.getUniformLocation(program, 'uAspect'), canvas.value.width / canvas.value.height)
  gl.uniform1f(gl.getUniformLocation(program, 'uPointSize'), pointSize.value * Math.min(2, window.devicePixelRatio || 1))
  gl.uniform1f(gl.getUniformLocation(program, 'uFocusX'), focusX.value)
  gl.uniform1f(gl.getUniformLocation(program, 'uFocusZ'), focusZ.value)
  gl.uniform1f(gl.getUniformLocation(program, 'uColorMode'), ({ source: 0, height: 1, mask: 2, confidence: 3, semantic: 4 } as const)[colorMode.value])
  gl.uniform1f(gl.getUniformLocation(program, 'uTargetOnly'), targetOnly.value ? 1 : 0)
  gl.uniform1f(gl.getUniformLocation(program, 'uThreshold'), thresholdValue.value)
  if (renderedPointCount.value) gl.drawArrays(gl.POINTS, 0, renderedPointCount.value)
  animationFrame = requestAnimationFrame(render)
}

async function loadSource() {
  abortController?.abort()
  header.value = null
  renderedPointCount.value = 0
  progress.value = 0
  error.value = ''
  resultError.value = ''
  resultAvailable.value = false
  semanticAvailable.value = false
  if ((!props.sourceUrl && !props.previewUrl) || !gl) return
  const controller = new AbortController()
  abortController = controller
  loading.value = true
  try {
    const preview = props.previewUrl ? await loadPointVisualizationPreview(props.previewUrl, controller.signal) : null
    const semanticLabelsPromise = props.semanticLabelsUrl
      ? loadNpzArray(props.semanticLabelsUrl, 'point_labels', controller.signal).catch((reason) => { if (!controller.signal.aborted) resultError.value = reason instanceof Error ? reason.message : '语义标签读取失败'; return null })
      : Promise.resolve(null)
    const [cloud, maskArray, probabilityArray, semanticLabels] = preview
      ? await Promise.all([Promise.resolve(preview.cloud), Promise.resolve({ data: preview.targetMask }), Promise.resolve({ data: preview.targetProbabilities }), semanticLabelsPromise])
      : await Promise.all([
          loadLasPointCloud(props.sourceUrl as string, props.pointBudget, controller.signal, (value) => { if (!controller.signal.aborted) progress.value = value }, true),
          props.targetMaskUrl ? loadNpzArray(props.targetMaskUrl, props.targetMaskArrayName, controller.signal).catch((reason) => { if (!controller.signal.aborted) resultError.value = reason instanceof Error ? reason.message : '目标掩膜读取失败'; return null }) : Promise.resolve(null),
          props.targetProbabilitiesUrl ? loadNpzArray(props.targetProbabilitiesUrl, 'target_probabilities', controller.signal).catch((reason) => { if (!controller.signal.aborted) resultError.value = reason instanceof Error ? reason.message : '目标概率读取失败'; return null }) : Promise.resolve(null),
          semanticLabelsPromise,
        ])
    if (controller.signal.aborted || abortController !== controller) return
    header.value = cloud.header
    renderedPointCount.value = cloud.renderedPointCount
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, cloud.positions, gl.STATIC_DRAW)
    gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, cloud.colors, gl.STATIC_DRAW)
    const semanticSource = semanticLabels?.data
    const maskSource = semanticSource || maskArray?.data
    const probabilitySource = probabilityArray?.data
    const sampledMask = new Float32Array(cloud.renderedPointCount)
    const sampledProbabilities = new Float32Array(cloud.renderedPointCount)
    for (let index = 0; index < cloud.sourceIndices.length; index += 1) {
      const sourceIndex = cloud.sourceIndices[index]
      sampledMask[index] = Number(semanticSource?.[sourceIndex] ?? maskSource?.[preview ? index : sourceIndex] ?? 0)
      sampledProbabilities[index] = Number(probabilitySource?.[preview ? index : sourceIndex] || 0)
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, targetBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, sampledMask, gl.STATIC_DRAW)
    gl.bindBuffer(gl.ARRAY_BUFFER, probabilityBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, sampledProbabilities, gl.STATIC_DRAW)
    resultAvailable.value = Boolean(maskArray || probabilityArray)
    semanticAvailable.value = Boolean(semanticLabels)
    if (semanticAvailable.value) colorMode.value = 'semantic'
    else if (resultAvailable.value) colorMode.value = 'mask'
    focusOnProjected()
    progress.value = 100
  } catch (reason) {
    if (!controller.signal.aborted && abortController === controller) error.value = reason instanceof Error ? reason.message : '点云加载失败'
  } finally {
    if (!controller.signal.aborted && abortController === controller) loading.value = false
  }
}

function pointerDown(event: PointerEvent) {
  dragging = true
  pointerX = event.clientX
  pointerY = event.clientY
  canvas.value?.setPointerCapture(event.pointerId)
}

function pointerMove(event: PointerEvent) {
  if (!dragging) return
  yaw.value += (event.clientX - pointerX) * 0.007
  pitch.value = Math.min(1.15, Math.max(-1.45, pitch.value + (event.clientY - pointerY) * 0.007))
  pointerX = event.clientX
  pointerY = event.clientY
}

function pointerUp(event: PointerEvent) {
  dragging = false
  canvas.value?.releasePointerCapture(event.pointerId)
}

function wheel(event: WheelEvent) {
  distance.value = Math.min(7, Math.max(1.45, distance.value + event.deltaY * 0.0025))
}

function resetCamera() {
  yaw.value = -0.7
  pitch.value = -0.72
  distance.value = 3.1
  focusX.value = 0
  focusZ.value = 0
}

function focusOnProjected() {
  if (!header.value || !props.focusProjected) {
    focusX.value = 0
    focusZ.value = 0
    return
  }
  const bounds = header.value.bounds
  const span = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY, 1)
  focusX.value = (props.focusProjected.x - (bounds.minX + bounds.maxX) / 2) / span * 2
  focusZ.value = -(props.focusProjected.y - (bounds.minY + bounds.maxY) / 2) / span * 2
  distance.value = 2.25
  if (resultAvailable.value) colorMode.value = 'mask'
}

function selectColorMode(value: string) {
  colorMode.value = value as ColorMode
}

onMounted(() => {
  try {
    initializeRenderer()
    loadSource()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'WebGL 初始化失败'
  }
})

watch([() => props.sourceUrl, () => props.previewUrl, () => props.targetMaskUrl, () => props.targetMaskArrayName, () => props.targetProbabilitiesUrl, () => props.semanticLabelsUrl], loadSource)
watch(() => props.appliedThreshold, (value) => { thresholdValue.value = value })
watch(() => props.focusProjected, focusOnProjected, { deep: true })

onBeforeUnmount(() => {
  abortController?.abort()
  cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
  if (gl) {
    if (positionBuffer) gl.deleteBuffer(positionBuffer)
    if (colorBuffer) gl.deleteBuffer(colorBuffer)
    if (targetBuffer) gl.deleteBuffer(targetBuffer)
    if (probabilityBuffer) gl.deleteBuffer(probabilityBuffer)
    if (program) gl.deleteProgram(program)
  }
})
</script>

<template>
  <div class="relative h-full min-h-[420px] w-full overflow-hidden bg-[#030a12]">
    <div class="pointer-events-none absolute inset-0 z-[1] opacity-25 [background-image:radial-gradient(circle_at_center,rgba(34,211,238,.16),transparent_58%)]" />
    <canvas
      ref="canvas"
      class="absolute inset-0 h-full w-full cursor-grab touch-none active:cursor-grabbing"
      aria-label="WebGL 三维点云查看器"
      @pointerdown="pointerDown"
      @pointermove="pointerMove"
      @pointerup="pointerUp"
      @pointercancel="pointerUp"
      @wheel.prevent="wheel"
    />

    <div class="pointer-events-none absolute left-4 top-4 z-10">
      <div class="flex items-center gap-2 text-sm font-semibold text-white"><span class="grid h-8 w-8 place-items-center rounded-lg border border-cyan-300/20 bg-cyan-300/10 text-cyan-200"><SafeIcon name="Orbit" :size="16" /></span>{{ title }}</div>
      <p class="mt-1.5 pl-10 text-[10px] text-slate-400">拖动旋转 · 滚轮缩放 · 浏览器实时渲染</p>
    </div>

    <div v-if="focusProjected && focusLabel && !loading" class="pointer-events-none absolute left-1/2 top-4 z-10 -translate-x-1/2 rounded-xl border border-cyan-200/20 bg-[#07111f]/85 px-3 py-2 text-center shadow-lg backdrop-blur">
      <p class="text-[9px] tracking-[0.14em] text-cyan-300">空间联动目标</p>
      <p class="mt-1 max-w-[260px] truncate text-[11px] font-semibold text-white">{{ focusLabel }}</p>
    </div>

    <div class="absolute right-4 top-4 z-10 flex max-w-[70%] flex-wrap items-center justify-end gap-1 rounded-xl border border-white/10 bg-[#07111f]/80 p-1 backdrop-blur">
      <button v-for="mode in resultModes" :key="mode.id" type="button" class="rounded-lg px-2.5 py-1.5 text-[10px] transition" :class="colorMode === mode.id ? 'bg-cyan-300/15 text-cyan-100' : 'text-slate-400 hover:bg-white/5'" @click="selectColorMode(mode.id)">{{ mode.label }}</button>
      <span class="mx-1 h-5 w-px bg-white/10" />
      <button type="button" class="grid h-7 w-7 place-items-center rounded-lg text-slate-300 hover:bg-white/10" title="减小点尺寸" @click="pointSize = Math.max(1, pointSize - 0.5)"><SafeIcon name="Minus" :size="12" /></button>
      <button type="button" class="grid h-7 w-7 place-items-center rounded-lg text-slate-300 hover:bg-white/10" title="增大点尺寸" @click="pointSize = Math.min(5, pointSize + 0.5)"><SafeIcon name="Plus" :size="12" /></button>
      <button type="button" class="grid h-7 w-7 place-items-center rounded-lg text-slate-300 hover:bg-white/10" title="复位视角" @click="resetCamera"><SafeIcon name="RotateCcw" :size="12" /></button>
    </div>

    <div v-if="semanticAvailable && !loading" class="absolute left-4 top-20 z-10 w-[270px] rounded-2xl border border-cyan-300/15 bg-[#07111f]/88 p-3 backdrop-blur">
      <div class="flex items-center justify-between gap-3"><span class="flex items-center gap-2 text-[11px] font-semibold text-cyan-100"><SafeIcon name="Layers3" :size="14" class="text-cyan-300" />点云语义分类</span><span class="rounded-md bg-cyan-300/10 px-2 py-1 text-[9px] text-cyan-200">真实标签</span></div>
      <div class="mt-3 max-h-56 space-y-1.5 overflow-y-auto pr-1"><div v-for="item in semanticClasses || []" :key="item.classId" class="flex items-center gap-2 rounded-lg bg-black/20 px-2.5 py-2"><span class="h-2.5 w-2.5 shrink-0 rounded-full" :style="{ backgroundColor: semanticPalette[item.classId - 1] || '#94a3b8', boxShadow: `0 0 10px ${semanticPalette[item.classId - 1] || '#94a3b8'}` }" /><span class="min-w-0 flex-1 truncate text-[10px] text-slate-200">{{ item.className }}</span><span class="font-mono text-[9px] text-slate-400">{{ (item.pointRatio * 100).toFixed(1) }}%</span></div></div>
      <p v-if="!(semanticClasses || []).length" class="mt-3 text-[9px] leading-4 text-slate-400">点级语义标签已加载，类别摘要暂不可用。</p>
    </div>

    <div v-else-if="resultAvailable && !loading" class="absolute left-4 top-20 z-10 w-[250px] rounded-2xl border border-orange-300/15 bg-[#07111f]/82 p-3 backdrop-blur">
      <div class="flex items-center justify-between gap-3"><span class="flex items-center gap-2 text-[11px] font-semibold text-orange-100"><SafeIcon name="ScanSearch" :size="14" class="text-orange-300" />真实识别结果</span><button type="button" class="rounded-lg border px-2 py-1 text-[9px] transition" :class="targetOnly ? 'border-orange-300/25 bg-orange-300/15 text-orange-100' : 'border-white/10 text-slate-400'" @click="targetOnly = !targetOnly">{{ targetOnly ? '显示全部' : '仅看目标' }}</button></div>
      <div class="mt-3 grid grid-cols-2 gap-2"><div class="rounded-lg bg-black/25 p-2"><span class="text-[9px] text-slate-500">目标点</span><strong class="mt-1 block text-xs text-orange-200">{{ selectedPoints?.toLocaleString('zh-CN') || '—' }}</strong></div><div class="rounded-lg bg-black/25 p-2"><span class="text-[9px] text-slate-500">目标占比</span><strong class="mt-1 block text-xs text-orange-200">{{ selectedRatioLabel }}</strong></div></div>
      <div class="mt-3"><div class="mb-1.5 flex items-center justify-between text-[9px]"><span class="text-slate-400">动态置信阈值</span><span class="font-mono text-cyan-200">{{ thresholdValue.toFixed(2) }}</span></div><input v-model.number="thresholdValue" type="range" min="0.02" max="0.55" step="0.01" class="w-full accent-orange-400" aria-label="目标置信阈值"></div>
      <div class="mt-2 h-1.5 rounded-full bg-gradient-to-r from-blue-700 via-cyan-400 via-amber-300 to-red-500" /><div class="mt-1 flex justify-between text-[8px] text-slate-600"><span>低置信</span><span>高置信</span></div>
      <p v-if="resultError" class="mt-2 text-[9px] leading-4 text-amber-200">{{ resultError }}</p>
    </div>

    <div v-else-if="resultError && !loading" class="absolute left-4 top-20 z-10 max-w-[300px] rounded-xl border border-amber-300/20 bg-[#17130b]/90 px-3 py-2 text-[10px] leading-5 text-amber-100 backdrop-blur">
      {{ resultError }}
    </div>

    <div v-if="loading" class="absolute inset-0 z-20 grid place-items-center bg-[#030a12]/78 backdrop-blur-sm">
      <div class="w-64 text-center"><div class="relative mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200"><SafeIcon name="ScanLine" :size="24" class="animate-pulse" /></div><p class="mt-4 text-sm font-medium text-white">正在构建三维场景</p><p class="mt-1 text-[11px] text-slate-400">{{ previewUrl ? '载入全场景均匀预览' : '载入原始点云并进行全局均匀抽样' }}</p><div class="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10"><div class="h-full rounded-full bg-gradient-to-r from-cyan-400 to-violet-400 transition-all" :style="{ width: `${progress}%` }" /></div><p class="mt-2 font-mono text-[10px] text-cyan-200">{{ progress }}%</p></div>
    </div>

    <div v-else-if="error || (!sourceUrl && !previewUrl)" class="absolute inset-0 z-10 grid place-items-center">
      <div class="max-w-sm px-6 text-center"><SafeIcon :name="error ? 'TriangleAlert' : 'Box'" :size="38" class="mx-auto text-slate-600" /><p class="mt-3 text-sm font-medium text-slate-300">{{ error || '当前任务未提供 LAS 点云' }}</p><p class="mt-2 text-[11px] leading-5 text-slate-500">上传带空间坐标的 LAS 文件后，系统将在这里进行真实 WebGL 渲染。</p></div>
    </div>

    <div v-if="header && !loading" class="pointer-events-none absolute bottom-4 left-4 right-4 z-10 flex flex-wrap items-end justify-between gap-3">
      <div class="grid grid-cols-3 gap-2 sm:grid-cols-5">
        <div class="rounded-lg border border-white/10 bg-black/50 px-3 py-2 backdrop-blur"><div class="text-[9px] text-slate-500">源点数量</div><strong class="mt-0.5 block text-xs text-white">{{ totalPointLabel }}</strong></div>
        <div class="rounded-lg border border-white/10 bg-black/50 px-3 py-2 backdrop-blur"><div class="text-[9px] text-slate-500">实时渲染</div><strong class="mt-0.5 block text-xs text-cyan-200">{{ renderedPointLabel }}</strong></div>
        <div class="rounded-lg border border-white/10 bg-black/50 px-3 py-2 backdrop-blur"><div class="text-[9px] text-slate-500">高程范围</div><strong class="mt-0.5 block text-xs text-emerald-200">{{ elevationLabel }}</strong></div>
        <div v-if="resultAvailable" class="rounded-lg border border-orange-300/15 bg-black/50 px-3 py-2 backdrop-blur"><div class="text-[9px] text-slate-500">目标占比</div><strong class="mt-0.5 block text-xs text-orange-200">{{ selectedRatioLabel }}</strong></div>
        <div v-if="resultAvailable" class="rounded-lg border border-cyan-300/15 bg-black/50 px-3 py-2 backdrop-blur"><div class="text-[9px] text-slate-500">执行可信度</div><strong class="mt-0.5 block text-xs text-cyan-200">{{ confidenceLabel }}</strong></div>
      </div>
      <span class="rounded-lg border border-emerald-300/15 bg-emerald-300/10 px-3 py-2 text-[10px] font-semibold text-emerald-200">WebGL · {{ header.version === 'preview' ? '空间均匀预览' : `LAS ${header.version} · 点格式 ${header.pointFormat}` }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { fromUrl } from 'geotiff'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  url?: string
  mediaType?: string
  alt?: string
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
const loading = ref(false)
const error = ref('')
let controller: AbortController | null = null

const isTiff = computed(() => /tiff?/i.test(props.mediaType || '') || /\.tiff?(?:\?|$)/i.test(props.url || ''))

async function renderTiff() {
  controller?.abort()
  error.value = ''
  if (!props.url || !isTiff.value) return
  const request = new AbortController()
  controller = request
  loading.value = true
  try {
    const tiff = await fromUrl(props.url, {}, request.signal)
    const image = await tiff.getImage()
    const sourceWidth = image.getWidth()
    const sourceHeight = image.getHeight()
    const scale = Math.min(1, 2048 / Math.max(sourceWidth, sourceHeight))
    const width = Math.max(1, Math.round(sourceWidth * scale))
    const height = Math.max(1, Math.round(sourceHeight * scale))
    const rgb = await image.readRGB({ width, height, interleave: true, signal: request.signal })
    if (request.signal.aborted || controller !== request || !canvas.value) return
    const pixels = new Uint8ClampedArray(width * height * 4)
    for (let source = 0, target = 0; source < rgb.length; source += 3, target += 4) {
      pixels[target] = Number(rgb[source])
      pixels[target + 1] = Number(rgb[source + 1])
      pixels[target + 2] = Number(rgb[source + 2])
      pixels[target + 3] = 255
    }
    canvas.value.width = width
    canvas.value.height = height
    canvas.value.getContext('2d')?.putImageData(new ImageData(pixels, width, height), 0, 0)
  } catch (reason) {
    if (!request.signal.aborted && controller === request) error.value = reason instanceof Error ? reason.message : 'GeoTIFF 读取失败'
  } finally {
    if (!request.signal.aborted && controller === request) loading.value = false
  }
}

watch([() => props.url, isTiff], () => { void renderTiff() }, { immediate: true, flush: 'post' })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <div class="relative h-full w-full overflow-hidden bg-[#030a12]">
    <canvas v-if="isTiff" ref="canvas" class="h-full w-full object-contain" :aria-label="alt || 'GeoTIFF 影像'" />
    <img v-else-if="url" :src="url" :alt="alt || '遥感影像'" class="h-full w-full object-contain" draggable="false">
    <div v-if="loading" class="absolute inset-0 grid place-items-center bg-[#030a12]/75 backdrop-blur-sm"><div class="text-center"><SafeIcon name="LoaderCircle" :size="26" class="mx-auto animate-spin text-cyan-300" /><p class="mt-2 text-[11px] text-slate-300">正在解析高分辨率正射影像</p><p class="mt-1 text-[9px] text-slate-500">浏览器端按显示尺寸降采样</p></div></div>
    <div v-else-if="error || !url" class="absolute inset-0 grid place-items-center"><div class="max-w-xs px-5 text-center"><SafeIcon name="ImageOff" :size="28" class="mx-auto text-slate-600" /><p class="mt-2 text-[11px] text-slate-400">{{ error || '暂无可显示影像' }}</p></div></div>
  </div>
</template>

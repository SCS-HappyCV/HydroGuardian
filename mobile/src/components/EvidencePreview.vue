<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { IonIcon, IonSpinner } from '@ionic/vue'
import { analyticsOutline, documentTextOutline, imageOutline, reloadOutline } from 'ionicons/icons'
import { resolveArtifactPreview } from '@/services/artifactPreviewService'

const props = defineProps<{
  url?: string
  alt: string
  kind?: 'image' | 'dataset' | 'report'
  mediaType?: string
}>()

const resolvedUrl = ref('')
const state = ref<'empty' | 'loading' | 'ready' | 'error'>('empty')
let requestVersion = 0

const label = computed(() => state.value === 'error' ? '影像暂时无法加载' : '暂无影像预览')
const formatLabel = computed(() => {
  if (props.mediaType === 'application/json') return 'JSON 结构化报告'
  if (props.mediaType === 'application/octet-stream') return '模型数值数据集'
  return props.kind === 'report' ? '结构化分析报告' : '模型分析数据集'
})

async function load() {
  const currentVersion = ++requestVersion
  resolvedUrl.value = ''
  if (props.kind && props.kind !== 'image') {
    state.value = 'empty'
    return
  }
  if (!props.url) {
    state.value = 'empty'
    return
  }
  state.value = 'loading'
  try {
    const url = await resolveArtifactPreview(props.url)
    if (currentVersion !== requestVersion) return
    resolvedUrl.value = url
    state.value = 'ready'
  } catch {
    if (currentVersion === requestVersion) state.value = 'error'
  }
}

function handleImageError() {
  resolvedUrl.value = ''
  state.value = 'error'
}

watch(() => props.url, load, { immediate: true })
onBeforeUnmount(() => { requestVersion += 1 })
</script>

<template>
  <div class="evidence-preview" :class="`is-${state}`">
    <img v-if="state === 'ready'" :src="resolvedUrl" :alt="alt" @error="handleImageError" />
    <template v-else-if="state === 'loading'">
      <IonSpinner name="crescent" />
      <span>正在加载证据影像</span>
    </template>
    <button v-else-if="state === 'error'" type="button" @click="load">
      <IonIcon :icon="reloadOutline" />
      <span>{{ label }}</span>
      <small>点击重试</small>
    </button>
    <template v-else-if="kind === 'report'">
      <IonIcon :icon="documentTextOutline" />
      <strong>分析报告</strong>
      <span>{{ formatLabel }}</span>
    </template>
    <template v-else-if="kind === 'dataset'">
      <IonIcon :icon="analyticsOutline" />
      <strong>数值数据</strong>
      <span>{{ formatLabel }}</span>
    </template>
    <template v-else>
      <IonIcon :icon="imageOutline" />
      <span>{{ label }}</span>
    </template>
  </div>
</template>

<style scoped>
.evidence-preview { display: grid; width: 100%; height: 92px; place-items: center; overflow: hidden; color: #6f8399; background: radial-gradient(circle at 50% 0, rgba(85,216,223,.13), transparent 65%), #07111f; font-size: 9px; }
.evidence-preview img { width: 100%; height: 100%; object-fit: cover; }
.evidence-preview ion-icon { font-size: 22px; }
.evidence-preview ion-spinner { width: 20px; height: 20px; color: #55d8df; }
.evidence-preview.is-loading { align-content: center; gap: 7px; }
.evidence-preview.is-empty { align-content: center; gap: 6px; }
.evidence-preview strong { color: #aac3d5; font-size: 10px; }
.evidence-preview button { display: grid; width: 100%; height: 100%; border: 0; place-content: center; place-items: center; gap: 4px; color: #89a1b8; background: transparent; font: inherit; }
.evidence-preview button small { color: #55d8df; font-size: 8px; }
</style>

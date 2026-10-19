<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { remoteAgentApi } from '@/api/remote-agent-api'
import type { RemoteArtifactRecord } from '@/lib/remote-agent-types'
import type { RemoteWorkorderEvidence } from '@/lib/remote-workorder-types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import SafeIcon from '@/components/common/SafeIcon.vue'
import WebglPointCloudViewer from '@/components/common/WebglPointCloudViewer.vue'

interface EvidenceDisplayItem {
  evidence: RemoteWorkorderEvidence
  artifact?: RemoteArtifactRecord
  downloadUrl?: string
  loading: boolean
  error?: string
}

const props = defineProps<{ evidence: RemoteWorkorderEvidence[] }>()
const items = ref<EvidenceDisplayItem[]>([])
const previewItem = ref<EvidenceDisplayItem | null>(null)
const previewOpen = ref(false)
const comparisonSplit = ref(52)

const sourceItems = computed(() => items.value.filter((item) => item.evidence.evidence_type === 'source'))
const fieldItems = computed(() => items.value.filter((item) => item.evidence.evidence_type !== 'source'))
const baselineImage = computed(() => sourceItems.value.find((item) => item.evidence.metadata.role === 'after_image_path' && isImage(item))
  || sourceItems.value.find((item) => isImage(item)))
const fieldImage = computed(() => [...fieldItems.value].reverse().find((item) => isImage(item)))
const canCompareClosure = computed(() => Boolean(baselineImage.value?.downloadUrl && fieldImage.value?.downloadUrl))

function filename(item: EvidenceDisplayItem): string {
  const key = item.artifact?.object_key
  return key?.split('/').at(-1) || item.evidence.title
}

function mediaType(item: EvidenceDisplayItem): string {
  return item.artifact?.media_type || item.evidence.media_type || 'application/octet-stream'
}

function isImage(item: EvidenceDisplayItem): boolean {
  return mediaType(item).startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(filename(item))
}

function isPointCloud(item: EvidenceDisplayItem): boolean {
  return mediaType(item).includes('las') || /\.las$/i.test(filename(item))
}

function formatSize(value?: number | null): string {
  if (!value) return '大小待读取'
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 ** 2).toFixed(1)} MB`
}

function typeLabel(item: EvidenceDisplayItem): string {
  if (isImage(item)) return '影像'
  if (isPointCloud(item)) return '三维点云'
  if (mediaType(item).includes('json')) return '分析报告'
  if (/\.(npz|npy)$/i.test(filename(item))) return '模型数据'
  return '附件'
}

async function hydrateEvidence(evidence: RemoteWorkorderEvidence): Promise<EvidenceDisplayItem> {
  const item: EvidenceDisplayItem = { evidence, loading: Boolean(evidence.artifact_id) }
  if (!evidence.artifact_id) return item
  try {
    const [artifact, downloadUrl] = await Promise.all([
      remoteAgentApi.getArtifact(evidence.artifact_id),
      remoteAgentApi.getDownloadUrl(evidence.artifact_id),
    ])
    return { evidence, artifact, downloadUrl, loading: false }
  } catch (error) {
    return { evidence, loading: false, error: error instanceof Error ? error.message : '附件读取失败' }
  }
}

async function loadEvidence() {
  const seed = props.evidence.map((evidence) => ({ evidence, loading: Boolean(evidence.artifact_id) }))
  items.value = seed
  items.value = await Promise.all(props.evidence.map(hydrateEvidence))
}

function openPreview(item: EvidenceDisplayItem) {
  if (!item.downloadUrl) {
    toast.error(item.error || '附件暂时无法预览')
    return
  }
  if (!isImage(item) && !isPointCloud(item)) {
    download(item)
    return
  }
  previewItem.value = item
  previewOpen.value = true
}

function download(item: EvidenceDisplayItem) {
  if (!item.downloadUrl) {
    toast.error(item.error || '附件暂时无法下载')
    return
  }
  const anchor = document.createElement('a')
  anchor.href = item.downloadUrl
  anchor.download = filename(item)
  anchor.target = '_blank'
  anchor.rel = 'noopener noreferrer'
  anchor.click()
}

watch(() => props.evidence, loadEvidence, { immediate: true, deep: true })
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-border/60 bg-card/40">
    <header class="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 px-5 py-4">
      <div>
        <div class="flex items-center gap-2">
          <span class="grid h-8 w-8 place-items-center rounded-lg bg-cyan-400/10 text-cyan-300"><SafeIcon name="Images" :size="16" /></span>
          <h2 class="text-sm font-semibold text-foreground">真实证据附件</h2>
          <Badge variant="outline" class="border-cyan-300/20 bg-cyan-300/[0.06] text-cyan-200">{{ items.length }} 项</Badge>
        </div>
        <p class="mt-1.5 pl-10 text-xs text-muted-foreground">Agent 分析产物与现场回传材料统一归档，可追溯、预览和下载。</p>
      </div>
      <div class="flex items-center gap-4 text-[11px] text-muted-foreground">
        <span class="flex items-center gap-1.5"><i class="h-2 w-2 rounded-full bg-cyan-300" />Agent 证据 {{ sourceItems.length }}</span>
        <span class="flex items-center gap-1.5"><i class="h-2 w-2 rounded-full bg-emerald-300" />现场材料 {{ fieldItems.length }}</span>
      </div>
    </header>

    <div v-if="items.length" class="space-y-5 p-5">
      <section v-if="canCompareClosure" class="overflow-hidden rounded-2xl border border-emerald-300/20 bg-[#07111f]">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
          <div><div class="flex items-center gap-2 text-xs font-semibold text-white"><SafeIcon name="BetweenHorizontalStart" :size="14" class="text-emerald-300" />处置前后证据对照</div><p class="mt-1 text-[10px] text-slate-400">风险发现时相与现场处置后照片同屏核验</p></div>
          <span class="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2.5 py-1 text-[9px] font-semibold text-emerald-200">闭环证据已配对</span>
        </div>
        <div class="relative h-[360px] overflow-hidden bg-black">
          <img :src="baselineImage?.downloadUrl" alt="处置前证据" class="absolute inset-0 h-full w-full object-cover">
          <div class="absolute inset-y-0 right-0 overflow-hidden" :style="{ width: `${100 - comparisonSplit}%` }"><img :src="fieldImage?.downloadUrl" alt="处置后证据" class="absolute inset-y-0 right-0 h-full object-cover" :style="{ width: `${10000 / Math.max(1, 100 - comparisonSplit)}%` }"></div>
          <div class="absolute inset-y-0 w-px bg-emerald-200 shadow-[0_0_20px_#6ee7b7]" :style="{ left: `${comparisonSplit}%` }"><span class="absolute left-1/2 top-1/2 grid h-9 w-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-emerald-100/50 bg-[#07111f]/90 text-emerald-100"><SafeIcon name="MoveHorizontal" :size="15" /></span></div>
          <span class="absolute left-4 top-4 rounded-lg border border-white/10 bg-black/55 px-3 py-1.5 text-[10px] text-white backdrop-blur">处置前 · {{ baselineImage?.evidence.title }}</span>
          <span class="absolute right-4 top-4 rounded-lg border border-emerald-300/20 bg-black/55 px-3 py-1.5 text-[10px] text-emerald-100 backdrop-blur">处置后 · {{ fieldImage?.evidence.title }}</span>
          <div class="absolute bottom-4 left-1/2 flex w-64 -translate-x-1/2 items-center gap-3 rounded-xl border border-white/10 bg-black/60 px-4 py-2 backdrop-blur"><SafeIcon name="Columns2" :size="12" class="text-emerald-200" /><input v-model="comparisonSplit" type="range" min="8" max="92" class="min-w-0 flex-1 accent-emerald-300" aria-label="处置前后证据分割位置"><span class="font-mono text-[9px] text-emerald-100">{{ comparisonSplit }}%</span></div>
        </div>
      </section>

      <div v-for="group in [{ title: 'Agent 原始证据', subtitle: '形成风险判断时引用的模型产物', items: sourceItems, tone: 'cyan' }, { title: '现场反馈材料', subtitle: '现场人员提交的说明与处置后证据', items: fieldItems, tone: 'emerald' }]" :key="group.title" v-show="group.items.length" class="space-y-3">
        <div class="flex items-end justify-between gap-3">
          <div><h3 class="text-xs font-medium text-foreground">{{ group.title }}</h3><p class="mt-0.5 text-[10px] text-muted-foreground">{{ group.subtitle }}</p></div>
          <span class="text-[10px] text-muted-foreground">{{ group.items.length }} 项材料</span>
        </div>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <article v-for="item in group.items" :key="item.evidence.evidence_id" class="group overflow-hidden rounded-xl border border-border/50 bg-background/35 transition hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-lg hover:shadow-primary/5">
            <button type="button" class="relative block h-36 w-full overflow-hidden bg-muted/20 text-left" @click="openPreview(item)">
              <img v-if="isImage(item) && item.downloadUrl" :src="item.downloadUrl" :alt="item.evidence.title" class="h-full w-full object-cover transition duration-500 group-hover:scale-[1.04]" loading="lazy" />
              <div v-else class="grid h-full place-items-center">
                <div class="text-center"><SafeIcon :name="item.loading ? 'LoaderCircle' : isPointCloud(item) ? 'Box' : mediaType(item).includes('json') ? 'FileJson2' : 'FileArchive'" :size="30" :class="['mx-auto text-muted-foreground/60', item.loading && 'animate-spin']" /><p class="mt-2 text-[10px] text-muted-foreground">{{ item.loading ? '正在读取附件' : typeLabel(item) }}</p></div>
              </div>
              <span class="absolute left-2.5 top-2.5 rounded-md border border-white/10 bg-black/55 px-2 py-1 text-[9px] font-medium text-white backdrop-blur">{{ typeLabel(item) }}</span>
              <span v-if="item.error" class="absolute inset-x-2.5 bottom-2.5 rounded bg-destructive/85 px-2 py-1 text-[9px] text-white">{{ item.error }}</span>
              <span v-else-if="item.downloadUrl" class="absolute bottom-2.5 right-2.5 grid h-7 w-7 place-items-center rounded-full bg-black/60 text-white opacity-0 backdrop-blur transition group-hover:opacity-100"><SafeIcon :name="isImage(item) || isPointCloud(item) ? 'Maximize2' : 'Download'" :size="13" /></span>
            </button>
            <div class="space-y-3 p-3.5">
              <div class="min-w-0"><p class="truncate text-xs font-medium text-foreground" :title="filename(item)">{{ item.evidence.title || filename(item) }}</p><p class="mt-1 truncate text-[10px] text-muted-foreground">{{ filename(item) }}</p></div>
              <div class="flex items-center justify-between gap-2 border-t border-border/40 pt-2.5 text-[9px] text-muted-foreground"><span>{{ formatSize(item.artifact?.size_bytes) }}</span><span>{{ new Date(item.evidence.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }}</span><Button variant="ghost" size="icon" class="h-7 w-7" :disabled="!item.downloadUrl" title="下载附件" @click="download(item)"><SafeIcon name="Download" :size="13" /></Button></div>
            </div>
          </article>
        </div>
      </div>
    </div>
    <div v-else class="grid min-h-36 place-items-center p-6 text-center"><div><SafeIcon name="PackageOpen" :size="28" class="mx-auto text-muted-foreground/30" /><p class="mt-2 text-xs text-muted-foreground">该工单尚未归档附件</p></div></div>
  </section>

  <Dialog v-model:open="previewOpen">
    <DialogContent class="max-w-6xl border-border/70 bg-background/95 p-0 backdrop-blur-xl">
      <DialogHeader class="border-b border-border/50 px-5 py-4">
        <DialogTitle class="pr-8 text-sm">{{ previewItem?.evidence.title }}</DialogTitle>
        <DialogDescription class="flex flex-wrap gap-x-4 gap-y-1 text-[10px]"><span>{{ previewItem ? filename(previewItem) : '' }}</span><span>{{ previewItem ? formatSize(previewItem.artifact?.size_bytes) : '' }}</span><span v-if="previewItem?.artifact?.sha256">校验值 {{ previewItem.artifact.sha256.slice(0, 12) }}…</span></DialogDescription>
      </DialogHeader>
      <div class="flex max-h-[72vh] min-h-[520px] items-center justify-center overflow-hidden bg-black/75">
        <WebglPointCloudViewer v-if="previewItem?.downloadUrl && isPointCloud(previewItem)" :source-url="previewItem.downloadUrl" :title="previewItem.evidence.title" />
        <img v-else-if="previewItem?.downloadUrl" :src="previewItem.downloadUrl" :alt="previewItem.evidence.title" class="max-h-[66vh] max-w-full object-contain p-5" />
      </div>
      <div class="flex items-center justify-between gap-3 border-t border-border/50 px-5 py-3"><p class="text-[10px] text-muted-foreground">附件来自后端资产存储，当前地址仅用于本次查看。</p><Button size="sm" class="gap-2" @click="previewItem && download(previewItem)"><SafeIcon name="Download" :size="14" />下载原文件</Button></div>
    </DialogContent>
  </Dialog>
</template>

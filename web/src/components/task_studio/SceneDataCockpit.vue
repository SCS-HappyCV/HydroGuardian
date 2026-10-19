<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentDemoScenario } from '@/lib/agent-presentation-types'

const props = defineProps<{
  scenario?: AgentDemoScenario | null
  sceneName?: string
  sceneId?: string
  expanded?: boolean
  addedAssets?: string[]
}>()
const emit = defineEmits<{ toggle: [] }>()
const assets = [
  { label: '正射影像', icon: 'Image', color: 'text-primary' },
  { label: '点云几何', icon: 'Cuboid', color: 'text-violet-300' },
  { label: '前时相', icon: 'ImageMinus', color: 'text-accent' },
  { label: '后时相', icon: 'ImagePlus', color: 'text-accent' },
]
const roleForLabel = (label: string) => label.replace('点云几何', '点云').replace('前时相', '前时相影像').replace('后时相', '后时相影像')
const assetStatus = (label: string) => {
  const role = roleForLabel(label)
  if (props.addedAssets?.includes(role)) return '已加入'
  if (props.scenario?.timeline[0].snapshot.task.availableAssets.includes(role)) return '可用'
  return '缺失'
}
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-white/[0.08] bg-card/60 shadow-card">
    <div class="relative h-[210px] overflow-hidden bg-[#0b2630]">
      <svg class="absolute inset-0 h-full w-full opacity-90" viewBox="0 0 800 420" preserveAspectRatio="none" aria-label="水利场景预览">
        <defs><linearGradient id="river" x1="0" x2="1"><stop stop-color="#0e4651"/><stop offset="1" stop-color="#12343c"/></linearGradient></defs>
        <rect width="800" height="420" fill="url(#river)"/><path d="M-40 320 C180 180 260 390 430 250 S680 120 850 210 L850 420 -40 420Z" fill="#0b6070" opacity=".75"/><path d="M-40 300 C180 160 260 370 430 230 S680 100 850 190" fill="none" stroke="#53d8cf" stroke-width="5" opacity=".8"/><path d="M40 70 L730 350 M150 15 L520 390" stroke="#7e8a91" stroke-width="10" opacity=".25"/><path d="M360 270 l85 -34 70 20 -86 38z" fill="#ffbe55" opacity=".45"/><path d="M160 225 l70 -26 66 19 -69 31z" fill="#ff6262" opacity=".8"/><circle cx="195" cy="219" r="24" fill="none" stroke="#ff6262" stroke-width="3"/><circle cx="402" cy="269" r="20" fill="none" stroke="#ffbe55" stroke-width="3"/></svg>
      <div class="absolute left-4 top-4 rounded-lg border border-white/15 bg-black/30 px-3 py-2 backdrop-blur"><p class="text-[10px] text-white/60">场景预览</p><p class="mt-1 text-xs font-medium text-white">{{ sceneName || '滨河岸段预置场景' }}</p></div>
      <div class="absolute bottom-3 left-4 rounded-md bg-black/35 px-2 py-1 text-[10px] text-white/70">{{ sceneId || 'scene-riverbank-001' }} · 巡查范围已对齐</div>
    </div>
    <div class="space-y-3 p-4">
      <div class="flex items-center justify-between"><div><p class="text-sm font-semibold text-foreground">场景数据舱</p><p class="mt-1 text-[11px] text-muted-foreground">当前数据可支持多模态证据分析</p></div><button type="button" class="text-[11px] text-primary hover:underline" @click="emit('toggle')">{{ expanded ? '收起设置' : '更换场景 / 添加数据' }}</button></div>
      <div class="grid grid-cols-4 gap-2"><div v-for="asset in assets" :key="asset.label" class="rounded-lg border p-2 text-center" :class="assetStatus(asset.label) !== '缺失' ? 'border-accent/20 bg-accent/[0.05]' : 'border-amber-400/20 bg-amber-400/[0.05]'" ><SafeIcon :name="asset.icon" :size="16" class="mx-auto" :class="asset.color"/><p class="mt-1 text-[10px] text-card-foreground">{{ asset.label }}</p><span class="mt-1 block text-[9px]" :class="assetStatus(asset.label) !== '缺失' ? 'text-accent' : 'text-amber-300'">{{ assetStatus(asset.label) }}</span></div></div>
      <div v-if="expanded" class="rounded-xl border border-white/[0.07] bg-black/10 p-3"><slot /></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

defineEmits<{
  startDemo: []
  createTask: []
}>()

const evidencePoints = [
  { x: 62, y: 26, delay: '0s' },
  { x: 73, y: 19, delay: '.4s' },
  { x: 81, y: 35, delay: '.8s' },
  { x: 69, y: 48, delay: '1.2s' },
  { x: 88, y: 55, delay: '1.6s' },
  { x: 58, y: 63, delay: '2s' },
]
</script>

<template>
  <section class="relative min-h-[760px] overflow-hidden px-5 pb-20 pt-24 md:px-8 lg:px-12">
    <div class="competition-grid absolute inset-0 opacity-35" />
    <div class="absolute left-[8%] top-28 h-72 w-72 rounded-full bg-primary/10 blur-[100px]" />
    <div class="absolute right-[8%] top-20 h-80 w-80 rounded-full bg-accent/10 blur-[110px]" />

    <div class="relative z-10 mx-auto grid max-w-[1440px] items-center gap-14 lg:grid-cols-[0.88fr_1.12fr]">
      <div class="space-y-8">
        <div class="inline-flex items-center gap-2 rounded-full border border-accent/25 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent">
          <span class="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_10px_hsl(var(--accent))]" />
          水利多模态智能巡查平台
        </div>

        <div class="space-y-5">
          <p class="text-sm font-semibold uppercase tracking-[0.28em] text-primary">HydroGuardian</p>
          <h1 class="max-w-3xl text-5xl font-semibold leading-[1.08] tracking-[-0.04em] text-foreground md:text-6xl xl:text-7xl">
            让一句巡查任务
            <span class="block bg-gradient-to-r from-primary via-cyan-300 to-accent bg-clip-text text-transparent">
              驱动水利隐患闭环
            </span>
          </h1>
          <p class="max-w-2xl text-base leading-8 text-muted-foreground md:text-lg">
            自然语言编译为空间分析程序，融合正射影像、点云与前后时相证据，输出可解释、可排序、可复核的风险结果。
          </p>
        </div>

        <div class="rounded-2xl border border-white/10 bg-card/45 p-4 backdrop-blur-xl">
          <div class="mb-2 flex items-center gap-2 text-xs font-medium text-accent">
            <SafeIcon name="Sparkles" :size="15" />
            典型巡查任务
          </div>
          <p class="text-sm leading-6 text-card-foreground">
            “筛查近水扰动区域，重点识别细长沟渠并排除道路，按风险高低排序。”
          </p>
          <div class="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            <span class="rounded-md bg-primary/10 px-2 py-1">近水约束</span>
            <span class="rounded-md bg-primary/10 px-2 py-1">细长几何</span>
            <span class="rounded-md bg-primary/10 px-2 py-1">道路排除</span>
            <span class="rounded-md bg-primary/10 px-2 py-1">风险排序</span>
          </div>
        </div>

        <div class="flex flex-col gap-3 sm:flex-row">
          <Button size="lg" class="h-12 gap-2 px-7 text-base shadow-[0_0_32px_hsl(var(--primary)/0.24)]" @click="$emit('startDemo')">
            <SafeIcon name="Play" :size="18" />
            开始智能巡查
          </Button>
          <Button variant="outline" size="lg" class="h-12 gap-2 border-white/15 bg-white/[0.03] px-7 text-base" @click="$emit('createTask')">
            <SafeIcon name="PenLine" :size="18" />
            自定义巡查任务
          </Button>
        </div>
      </div>

      <div class="relative mx-auto w-full max-w-[760px]">
        <div class="scene-glow absolute inset-8 rounded-full blur-3xl" />
        <div class="scene-panel relative aspect-[1.18/1] overflow-hidden rounded-[28px] border border-white/10 bg-[#081827] shadow-2xl shadow-black/40">
          <div class="absolute inset-x-0 top-0 z-30 flex items-center justify-between border-b border-white/10 bg-[#07111f]/80 px-5 py-3 backdrop-blur-xl">
            <div class="flex items-center gap-2 text-xs text-card-foreground">
              <span class="h-2 w-2 rounded-full bg-[hsl(var(--success))] shadow-[0_0_8px_hsl(var(--success))]" />
              河岸场景 scene-riverbank-001
            </div>
            <div class="flex gap-2 text-[10px] text-muted-foreground">
              <span>正射影像</span><span>·</span><span>点云</span><span>·</span><span>时相变化</span>
            </div>
          </div>

          <svg class="absolute inset-0 h-full w-full" viewBox="0 0 760 640" preserveAspectRatio="xMidYMid slice" aria-label="水利场景智能分析示意图">
            <defs>
              <linearGradient id="terrain" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#153642" />
                <stop offset=".5" stop-color="#1c423b" />
                <stop offset="1" stop-color="#233a31" />
              </linearGradient>
              <linearGradient id="river" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#0d4b67" />
                <stop offset=".55" stop-color="#14749a" />
                <stop offset="1" stop-color="#0b3f62" />
              </linearGradient>
              <pattern id="field-grid" width="46" height="46" patternUnits="userSpaceOnUse" patternTransform="rotate(18)">
                <path d="M 46 0 L 0 0 0 46" fill="none" stroke="#9ad4bf" stroke-opacity=".09" stroke-width="1" />
              </pattern>
              <filter id="risk-glow"><feGaussianBlur stdDeviation="5" result="b" /><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            </defs>
            <rect width="760" height="640" fill="url(#terrain)" />
            <rect width="760" height="640" fill="url(#field-grid)" />
            <path d="M-60 80 C120 140 100 278 260 326 C430 377 450 506 820 566 L820 720 L-60 720Z" fill="url(#river)" />
            <path d="M-30 78 C135 143 117 267 271 315 C438 368 463 493 790 548" fill="none" stroke="#4ed8e4" stroke-opacity=".55" stroke-width="3" stroke-dasharray="8 8" />
            <path d="M470 75 L622 154 L554 252 L397 174Z" fill="#b8ad72" fill-opacity=".19" stroke="#d5cf94" stroke-opacity=".18" />
            <path d="M128 318 L221 347 L184 482 L90 448Z" fill="#83a463" fill-opacity=".22" />
            <path d="M486 364 C523 342 574 352 604 391 L568 420 C537 394 507 395 470 413Z" fill="#a96e4d" fill-opacity=".5" />
            <path d="M482 353 C536 319 601 340 629 395 L572 446 C533 415 496 418 449 438Z" fill="none" stroke="#ff5d5d" stroke-width="3" filter="url(#risk-glow)" />
            <path d="M491 363 C532 342 575 351 604 389" fill="none" stroke="#ffce73" stroke-width="5" stroke-linecap="round" />
            <line x1="445" y1="336" x2="394" y2="303" stroke="#2dd4bf" stroke-width="2" stroke-dasharray="5 5" />
            <text x="332" y="296" fill="#9fe9dd" font-size="13">距水线 18m</text>
            <g transform="translate(535 296)">
              <rect width="170" height="54" rx="10" fill="#07111f" fill-opacity=".86" stroke="#ff5d5d" stroke-opacity=".55" />
              <text x="14" y="22" fill="#ffffff" font-size="13" font-weight="600">R-01 疑似开挖沟渠</text>
              <text x="14" y="41" fill="#ff8b8b" font-size="11">高风险 · 92分</text>
            </g>
            <g transform="translate(122 174)">
              <rect width="146" height="48" rx="9" fill="#07111f" fill-opacity=".78" stroke="#2dd4bf" stroke-opacity=".35" />
              <text x="12" y="20" fill="#ffffff" font-size="12">三模态证据已对齐</text>
              <text x="12" y="37" fill="#80dacd" font-size="10">综合置信度 0.91</text>
            </g>
          </svg>

          <span
            v-for="point in evidencePoints"
            :key="`${point.x}-${point.y}`"
            class="evidence-point absolute z-20 h-1.5 w-1.5 rounded-full bg-violet-300"
            :style="{ left: `${point.x}%`, top: `${point.y}%`, animationDelay: point.delay }"
          />
          <div class="scan-line absolute inset-x-0 z-10 h-px bg-gradient-to-r from-transparent via-accent to-transparent" />

          <div class="absolute bottom-4 left-4 right-4 z-30 grid grid-cols-3 gap-2">
            <div class="scene-stat"><span>候选区域</span><strong>05</strong></div>
            <div class="scene-stat"><span>高风险</span><strong class="text-red-300">01</strong></div>
            <div class="scene-stat"><span>待复核</span><strong class="text-amber-300">01</strong></div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.competition-grid {
  background-image: linear-gradient(rgba(103, 183, 255, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(103, 183, 255, 0.05) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: linear-gradient(to bottom, black, transparent 90%);
}
.scene-glow { background: radial-gradient(circle, hsl(var(--primary) / .28), transparent 68%); }
.scene-panel::after { content: ''; position: absolute; inset: 0; pointer-events: none; box-shadow: inset 0 0 80px rgba(0,0,0,.38); }
.scan-line { animation: scan 5s ease-in-out infinite; box-shadow: 0 0 18px hsl(var(--accent)); }
.evidence-point { animation: point-pulse 2.4s ease-in-out infinite; box-shadow: 0 0 10px #a78bfa; }
.scene-stat { display: flex; align-items: center; justify-content: space-between; border: 1px solid rgba(255,255,255,.09); border-radius: 10px; background: rgba(7,17,31,.78); padding: 9px 11px; backdrop-filter: blur(12px); color: hsl(var(--muted-foreground)); font-size: 10px; }
.scene-stat strong { color: hsl(var(--foreground)); font-size: 16px; }
@keyframes scan { 0%, 100% { top: 15%; opacity: .2; } 50% { top: 82%; opacity: .9; } }
@keyframes point-pulse { 0%, 100% { opacity: .35; transform: scale(.75); } 50% { opacity: 1; transform: scale(1.4); } }
@media (prefers-reduced-motion: reduce) { .scan-line, .evidence-point { animation: none; } }
</style>

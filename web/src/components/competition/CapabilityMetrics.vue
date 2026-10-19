<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'

const capabilities = [
  { value: '7', unit: '步', title: '动态专家规划', description: '根据目标实时组合本次所需能力', icon: 'Network' },
  { value: '5', unit: '项', title: '证据产物', description: '语义、几何、变化与质量报告', icon: 'Layers3' },
  { value: '89', unit: '%', title: '结论置信度', description: '质量验证后输出可信风险结论', icon: 'ShieldCheck' },
  { value: '100', unit: '%', title: '闭环可追溯', description: '任务、证据、风险、工单与复核全关联', icon: 'GitBranch' },
]
</script>

<template>
  <section class="px-5 pb-24 pt-10 md:px-8 lg:px-12">
    <div class="mx-auto max-w-[1440px]">
      <div class="mb-9 text-center">
        <p class="mb-2 text-xs font-semibold uppercase tracking-[0.24em] text-primary">CORE CAPABILITIES</p>
        <h2 class="text-3xl font-semibold tracking-tight text-foreground md:text-4xl">创新不止于识别结果</h2>
        <p class="mx-auto mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">从任务理解到安全决策，每项能力都对应真实服务与结构化输出。</p>
      </div>

      <div class="grid gap-px overflow-hidden rounded-[24px] border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-4">
        <article v-for="capability in capabilities" :key="capability.title" class="group bg-[#091522] p-6 transition-colors hover:bg-[#0c1b2b]">
          <div class="mb-8 flex items-center justify-between">
            <div class="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary">
              <SafeIcon :name="capability.icon" :size="20" />
            </div>
            <SafeIcon name="ArrowUpRight" :size="16" class="text-muted-foreground/40 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-accent" />
          </div>
          <div class="flex items-baseline gap-1">
            <strong class="text-4xl font-semibold tracking-tight text-foreground">{{ capability.value }}</strong>
            <span class="text-sm text-accent">{{ capability.unit }}</span>
          </div>
          <h3 class="mt-3 text-sm font-semibold text-card-foreground">{{ capability.title }}</h3>
          <p class="mt-2 text-xs leading-5 text-muted-foreground">{{ capability.description }}</p>
        </article>
      </div>
    </div>
  </section>
</template>

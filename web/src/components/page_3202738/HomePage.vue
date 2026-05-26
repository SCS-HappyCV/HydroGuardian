
<script setup lang="ts">
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'

const isClient = ref(true)

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true
  })
})

const features = [
  {
    id: 'dashboard',
    title: '全局总览',
    description: '实时监控系统运行态势，快速感知风险分布与任务进度',
    icon: 'LayoutDashboard',
    href: './dashboard.html',
    color: 'from-primary/20 to-primary/5'
  },
  {
    id: 'task-studio',
    title: '任务工作坊',
    description: '通过自然语言或预设模板快速创建巡查任务，支持参数自定义',
    icon: 'Hammer',
    href: './task-studio.html',
    color: 'from-accent/20 to-accent/5'
  },
  {
    id: 'risk-workspace',
    title: '风险分析区',
    description: '集成 GIS 地图与证据图层，支持空间维度的风险点定位与分析',
    icon: 'Activity',
    href: './risk-workspace.html',
    color: 'from-[hsl(var(--warning))]/20 to-[hsl(var(--warning))]/5'
  },
  {
    id: 'workorder-center',
    title: '工单中心',
    description: '风险处置闭环管理，追踪工单流转与处理进度',
    icon: 'ClipboardList',
    href: './workorder-center.html',
    color: 'from-[hsl(var(--success))]/20 to-[hsl(var(--success))]/5'
  },
  {
    id: 'history',
    title: '历史回溯',
    description: '任务执行回放与结果对比，支持复盘分析与趋势追踪',
    icon: 'History',
    href: './history.html',
    color: 'from-accent/20 to-accent/5'
  },
  {
    id: 'knowledge',
    title: '知识库管理',
    description: '风险判定规则与处置建议模板的集中管理与版本控制',
    icon: 'BookOpen',
    href: './knowledge.html',
    color: 'from-primary/20 to-primary/5'
  }
]

const handleEnter = () => {
  window.location.href = './task-studio.html'
}

const handleFeatureClick = (href: string) => {
  window.location.href = href
}
</script>

<template>
  <div class="relative w-full">
    <!-- Animated background gradient -->
    <div class="absolute inset-0 overflow-hidden pointer-events-none">
      <div class="absolute top-0 left-1/4 w-96 h-96 bg-gradient-to-br from-primary/10 to-transparent rounded-full blur-3xl opacity-40 animate-pulse" />
      <div class="absolute bottom-1/3 right-1/4 w-80 h-80 bg-gradient-to-tl from-accent/10 to-transparent rounded-full blur-3xl opacity-30 animate-pulse" style="animation-delay: 1s" />
    </div>

    <!-- Hero Section -->
    <section class="relative z-10 min-h-screen flex flex-col items-center justify-center px-4 py-20 md:py-0">
      <div class="max-w-4xl mx-auto text-center space-y-8">
        <!-- Logo & Title -->
        <div class="space-y-4 animate-fade-in">
          <div class="inline-flex items-center justify-center">
            <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-2xl shadow-primary/30">
              <SafeIcon name="ShieldAlert" :size="32" class="text-primary-foreground" />
            </div>
          </div>
          
          <h1 class="text-5xl md:text-7xl font-bold tracking-tight bg-gradient-to-r from-foreground via-foreground to-foreground/70 bg-clip-text text-transparent">
            水域卫士
          </h1>
          
          <p class="text-xl md:text-2xl text-muted-foreground font-light leading-relaxed max-w-2xl mx-auto">
            智能水体风险监测与闭环处置系统
          </p>
        </div>

        <!-- Subtitle -->
        <div class="space-y-3 text-muted-foreground">
          <p class="text-base md:text-lg">
            通过 AI 驱动的风险识别、空间可视化分析与工单闭环管理
          </p>
          <p class="text-base md:text-lg">
            为水体安全保驾护航
          </p>
        </div>

        <!-- CTA Button -->
        <div class="pt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
          <Button
            size="lg"
            class="px-10 py-6 text-lg font-semibold bg-gradient-to-r from-primary to-accent hover:shadow-xl hover:shadow-primary/30 transition-all duration-300 hover:scale-105"
            @click="handleEnter"
          >
            <SafeIcon name="Zap" :size="20" class="mr-2" />
            进入功能
          </Button>
          
          <Button
            variant="outline"
            size="lg"
            class="px-10 py-6 text-lg font-semibold border-primary/30 hover:bg-primary/10 transition-all duration-300"
            @click="toast('功能文档正在准备中')"
          >
            <SafeIcon name="BookOpen" :size="20" class="mr-2" />
            查看文档
          </Button>
        </div>

        <!-- Quick Stats -->
        <div class="pt-12 grid grid-cols-3 gap-4 md:gap-8 max-w-2xl mx-auto">
          <div class="space-y-2">
            <div class="text-3xl md:text-4xl font-bold text-primary">7</div>
            <div class="text-sm text-muted-foreground">核心功能模块</div>
          </div>
          <div class="space-y-2">
            <div class="text-3xl md:text-4xl font-bold text-accent">∞</div>
            <div class="text-sm text-muted-foreground">可扩展规则引擎</div>
          </div>
          <div class="space-y-2">
            <div class="text-3xl md:text-4xl font-bold text-[hsl(var(--success))]">100%</div>
            <div class="text-sm text-muted-foreground">闭环追踪</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section class="relative z-10 py-20 md:py-32 px-4 bg-gradient-to-b from-transparent via-background/50 to-background">
      <div class="max-w-6xl mx-auto">
        <div class="text-center mb-16 space-y-4">
          <h2 class="text-4xl md:text-5xl font-bold tracking-tight">
            核心功能
          </h2>
          <p class="text-lg text-muted-foreground max-w-2xl mx-auto">
            完整的风险发现、分析、处置与复盘闭环
          </p>
        </div>

        <!-- Features Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div
            v-for="feature in features"
            :key="feature.id"
            class="group cursor-pointer"
            @click="handleFeatureClick(feature.href)"
          >
            <div class="h-full surface-base card-padding flex flex-col gap-4 transition-all duration-300 hover:surface-raised hover:shadow-lg hover:shadow-primary/10 hover:-translate-y-1">
              <!-- Icon -->
              <div :class="cn('w-12 h-12 rounded-lg bg-gradient-to-br flex items-center justify-center transition-transform group-hover:scale-110', feature.color)">
                <SafeIcon :name="feature.icon" :size="24" class="text-foreground" />
              </div>

              <!-- Content -->
              <div class="flex-1 space-y-2">
                <h3 class="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">
                  {{ feature.title }}
                </h3>
                <p class="text-sm text-muted-foreground leading-relaxed">
                  {{ feature.description }}
                </p>
              </div>

              <!-- Arrow Indicator -->
              <div class="flex items-center text-primary opacity-0 group-hover:opacity-100 transition-opacity text-sm font-medium">
                <span>了解更多</span>
                <SafeIcon name="ArrowRight" :size="16" class="ml-2 group-hover:translate-x-1 transition-transform" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="relative z-10 py-20 md:py-32 px-4">
      <div class="max-w-4xl mx-auto">
        <div class="surface-raised card-padding text-center space-y-6 border-primary/20">
          <h2 class="text-3xl md:text-4xl font-bold">
            准备好开始了吗？
          </h2>
          <p class="text-lg text-muted-foreground max-w-2xl mx-auto">
            立即进入系统，创建您的第一个巡查任务，开启智能风险监测之旅
          </p>
          
          <div class="pt-4">
            <Button
              size="lg"
              class="px-12 py-6 text-lg font-semibold bg-gradient-to-r from-primary to-accent hover:shadow-xl hover:shadow-primary/30 transition-all duration-300 hover:scale-105"
              @click="handleEnter"
            >
              <SafeIcon name="Play" :size="20" class="mr-2" />
              立即开始
            </Button>
          </div>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="relative z-10 border-t border-border/30 py-8 px-4 bg-background/50 backdrop-blur-sm">
      <div class="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
        <div class="flex items-center gap-2">
          <SafeIcon name="ShieldAlert" :size="16" class="text-primary" />
          <span>© 2026 水域卫士系统 - 智能水体风险监测平台</span>
        </div>
        <div class="flex items-center gap-6">
          <button class="hover:text-foreground transition-colors" @click="toast('隐私政策正在准备中')">
            隐私政策
          </button>
          <button class="hover:text-foreground transition-colors" @click="toast('服务条款正在准备中')">
            服务条款
          </button>
          <button class="hover:text-foreground transition-colors" @click="toast('联系我们功能正在准备中')">
            联系我们
          </button>
        </div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in {
  animation: fade-in 0.8s ease-out;
}
</style>

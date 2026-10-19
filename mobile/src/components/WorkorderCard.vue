<script setup lang="ts">
import { IonIcon } from '@ionic/vue'
import { chevronForward, locationOutline, timeOutline } from 'ionicons/icons'
import type { MobileWorkOrder } from '@/domain/workorder'
import { riskLevelLabels, statusLabels } from '@/domain/workorder'

defineProps<{ item: MobileWorkOrder }>()
</script>

<template>
  <article class="workorder-card surface">
    <div class="accent" :class="`accent-${item.riskLevel}`" />
    <div class="topline">
      <div class="tags">
        <span class="risk-tag" :class="`risk-${item.riskLevel}`">{{ riskLevelLabels[item.riskLevel] }}</span>
        <span class="status-tag">{{ statusLabels[item.status] }}</span>
      </div>
      <strong class="score">{{ item.confidence }}</strong>
    </div>
    <h2>{{ item.title }}</h2>
    <p class="summary">{{ item.summary }}</p>
    <div class="meta">
      <span><IonIcon :icon="locationOutline" />{{ item.area }} · {{ item.distanceMeters < 1000 ? `${item.distanceMeters}m` : `${(item.distanceMeters / 1000).toFixed(1)}km` }}</span>
      <span><IonIcon :icon="timeOutline" />{{ new Date(item.deadline).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }}</span>
    </div>
    <div class="footer">
      <span>{{ item.evidence.length }} 类证据已关联</span>
      <IonIcon :icon="chevronForward" />
    </div>
  </article>
</template>

<style scoped>
.workorder-card {
  position: relative;
  overflow: hidden;
  padding: 15px;
}

.accent {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
}

.accent-high { background: #ff5d5d; }
.accent-medium { background: #f5b942; }
.accent-review_required { background: #8b7cff; }

.topline,
.tags,
.meta,
.footer {
  display: flex;
  align-items: center;
}

.topline,
.footer {
  justify-content: space-between;
}

.tags {
  gap: 6px;
}

.risk-tag,
.status-tag {
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 9px;
  font-weight: 700;
}

.risk-high { background: rgba(255, 93, 93, 0.12); color: #ff837c; }
.risk-medium { background: rgba(245, 185, 66, 0.12); color: #ffd06b; }
.risk-review_required { background: rgba(139, 124, 255, 0.12); color: #b8adff; }
.status-tag { border: 1px solid rgba(148, 180, 208, 0.12); color: #9bb0c5; }
.score { color: #55d8df; font-size: 23px; }

h2 {
  margin: 13px 0 0;
  font-size: 15px;
  line-height: 1.45;
}

.summary {
  display: -webkit-box;
  overflow: hidden;
  margin: 7px 0 0;
  color: #8296ac;
  font-size: 11px;
  line-height: 1.6;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.meta {
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-top: 12px;
  color: #6f8399;
  font-size: 10px;
}

.meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.footer {
  margin-top: 12px;
  border-top: 1px solid rgba(148, 180, 208, 0.08);
  padding-top: 10px;
  color: #55d8df;
  font-size: 10px;
}
</style>

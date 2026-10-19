<script setup lang="ts">
import {
  IonButton,
  IonContent,
  IonIcon,
  IonLabel,
  IonSpinner,
  IonPage,
  IonRefresher,
  IonRefresherContent,
  IonSearchbar,
  IonSegment,
  IonSegmentButton,
  IonSelect,
  IonSelectOption,
} from '@ionic/vue'
import { optionsOutline, refreshOutline, searchOutline } from 'ionicons/icons'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import MobileHeader from '@/components/MobileHeader.vue'
import WorkorderCard from '@/components/WorkorderCard.vue'
import { taskDetailPath } from '@/router/paths'
import { useWorkorderStore } from '@/stores/workorders'

const router = useRouter()
const store = useWorkorderStore()
const {
  activeFilter,
  riskFilter,
  searchQuery,
  filteredItems,
  activeCount,
  reviewedCount,
  closedCount,
  lastRefreshedAt,
  loadError,
  initialized,
} = storeToRefs(store)

async function refresh(event: CustomEvent) {
  await store.refresh()
  await (event.target as HTMLIonRefresherElement).complete()
}

function clearFilters() {
  searchQuery.value = ''
  riskFilter.value = 'all'
}
</script>

<template>
  <IonPage>
    <MobileHeader title="现场任务" subtitle="水利风险处置与证据回传">
      <template #action>
        <div class="connection"><i />连接正常</div>
      </template>
    </MobileHeader>
    <IonContent>
      <IonRefresher slot="fixed" @ion-refresh="refresh">
        <IonRefresherContent pulling-text="下拉刷新" refreshing-spinner="crescent" />
      </IonRefresher>

      <div class="page-shell safe-area-bottom">
        <section class="summary surface">
          <div>
            <span>今日待办</span>
            <strong>{{ activeCount }}</strong>
          </div>
          <div>
            <span>等待复核</span>
            <strong>{{ reviewedCount }}</strong>
          </div>
          <div>
            <span>已闭环</span>
            <strong>{{ closedCount }}</strong>
          </div>
        </section>

        <div class="search-row">
          <IonSearchbar
            v-model="searchQuery"
            :search-icon="searchOutline"
            placeholder="搜索任务、区域或编号"
            mode="ios"
            class="task-search"
          />
          <IonSelect
            v-model="riskFilter"
            interface="popover"
            aria-label="风险等级筛选"
            class="risk-select"
          >
            <IonSelectOption value="all">全部等级</IonSelectOption>
            <IonSelectOption value="high">高风险</IonSelectOption>
            <IonSelectOption value="medium">中风险</IonSelectOption>
            <IonSelectOption value="review_required">待核验</IonSelectOption>
          </IonSelect>
        </div>

        <IonSegment v-model="activeFilter" mode="ios" class="filter">
          <IonSegmentButton value="active"><IonLabel>当前任务</IonLabel></IonSegmentButton>
          <IonSegmentButton value="reviewed"><IonLabel>待复核</IonLabel></IonSegmentButton>
          <IonSegmentButton value="closed"><IonLabel>已完成</IonLabel></IonSegmentButton>
        </IonSegment>

        <div class="list-context">
          <span><IonIcon :icon="optionsOutline" />{{ filteredItems.length }} 项任务</span>
          <small v-if="lastRefreshedAt">
            更新于 {{ new Date(lastRefreshedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
          </small>
        </div>

        <div v-if="!initialized" class="loading surface">
          <IonSpinner name="crescent" />
          <strong>正在同步现场任务</strong>
          <span>读取风险工单与最新处置状态</span>
        </div>
        <div v-else-if="loadError && !filteredItems.length" class="error surface">
          <strong>任务数据暂时无法读取</strong>
          <span>{{ loadError }}</span>
          <IonButton size="small" fill="outline" @click="store.refresh()">
            <IonIcon slot="start" :icon="refreshOutline" />重新加载
          </IonButton>
        </div>
        <div v-else-if="filteredItems.length" class="task-list">
          <div v-if="loadError" class="cache-notice">{{ loadError }}</div>
          <WorkorderCard
            v-for="item in filteredItems"
            :key="item.id"
            :item="item"
            @click="router.push(taskDetailPath(item.id))"
          />
        </div>
        <div v-else class="empty surface">
          <strong>当前没有相关任务</strong>
          <span>可以调整关键词或风险等级后重试</span>
          <IonButton size="small" fill="clear" @click="clearFilters">清除筛选</IonButton>
        </div>
      </div>
    </IonContent>
  </IonPage>
</template>

<style scoped>
.connection {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(57, 201, 138, 0.16);
  border-radius: 999px;
  background: rgba(57, 201, 138, 0.06);
  padding: 6px 9px;
  color: #63e3af;
  font-size: 9px;
}

.connection i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #39c98a;
  box-shadow: 0 0 8px #39c98a;
}

.summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  padding: 14px;
}

.summary div {
  text-align: center;
}

.summary div + div {
  border-left: 1px solid rgba(148, 180, 208, 0.1);
}

.summary span {
  display: block;
  color: #71849a;
  font-size: 9px;
}

.summary strong {
  display: block;
  margin-top: 5px;
  font-size: 21px;
}

.filter {
  margin: 10px 0 12px;
  --background: rgba(13, 31, 50, 0.9);
}

.search-row {
  display: grid;
  grid-template-columns: 1fr 92px;
  gap: 8px;
  margin-top: 13px;
}

.task-search {
  padding: 0;
  --background: rgba(13, 31, 50, 0.9);
  --border-radius: 13px;
  --box-shadow: none;
  --color: #dce8f3;
  --placeholder-color: #63778d;
  --icon-color: #71849a;
}

.risk-select {
  min-height: 42px;
  border: 1px solid rgba(148, 180, 208, 0.1);
  border-radius: 13px;
  padding: 0 10px;
  color: #9bb0c5;
  background: rgba(13, 31, 50, 0.9);
  font-size: 10px;
}

.list-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 2px 9px;
  color: #71849a;
  font-size: 9px;
}

.list-context span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.list-context small {
  font-size: 9px;
}

.task-list {
  display: grid;
  gap: 11px;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 45px 20px;
  color: #9bb0c5;
  font-size: 13px;
}

.empty span {
  margin-top: 6px;
  color: #63778d;
  font-size: 10px;
}

.empty ion-button {
  margin-top: 8px;
  font-size: 10px;
}

.error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 18px;
}

.error strong {
  font-size: 13px;
}

.error span {
  margin-top: 5px;
  color: #8296ac;
  font-size: 10px;
}

.error ion-button {
  margin: 10px 0 0;
}

.loading {
  display: flex;
  min-height: 170px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  color: #9bb0c5;
}

.loading ion-spinner { color: #55d8df; }
.loading strong { margin-top: 12px; font-size: 13px; }
.loading span { margin-top: 5px; color: #63778d; font-size: 9px; }
.cache-notice { border: 1px solid rgba(245,185,66,.16); border-radius: 11px; padding: 9px 11px; color: #ffd06b; background: rgba(245,185,66,.06); font-size: 9px; }
</style>

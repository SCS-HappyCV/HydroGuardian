<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  IonIcon,
  IonLabel,
  IonRouterOutlet,
  IonTabBar,
  IonTabButton,
  IonTabs,
} from '@ionic/vue'
import { clipboardOutline, mapOutline, personOutline, syncOutline } from 'ionicons/icons'

const route = useRoute()
const showTabBar = computed(() => ['/tabs/tasks', '/tabs/map', '/tabs/sync', '/tabs/profile'].includes(route.path))
</script>

<template>
  <IonTabs>
    <IonRouterOutlet />
    <IonTabBar v-if="showTabBar" slot="bottom">
      <IonTabButton tab="tasks" href="/tabs/tasks">
        <IonIcon :icon="clipboardOutline" />
        <IonLabel>任务</IonLabel>
      </IonTabButton>
      <IonTabButton tab="map" href="/tabs/map">
        <IonIcon :icon="mapOutline" />
        <IonLabel>地图</IonLabel>
      </IonTabButton>
      <IonTabButton tab="sync" href="/tabs/sync">
        <IonIcon :icon="syncOutline" />
        <IonLabel>同步</IonLabel>
      </IonTabButton>
      <IonTabButton tab="profile" href="/tabs/profile">
        <IonIcon :icon="personOutline" />
        <IonLabel>我的</IonLabel>
      </IonTabButton>
    </IonTabBar>
  </IonTabs>
</template>

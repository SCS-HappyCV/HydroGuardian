<script setup lang="ts">
import { IonHeader, IonToolbar } from '@ionic/vue'

defineProps<{
  title: string
  subtitle?: string
}>()
</script>

<template>
  <IonHeader class="ion-no-border">
    <IonToolbar>
      <div class="mobile-header">
        <div>
          <div class="brand">HydroGuardian</div>
          <h1>{{ title }}</h1>
          <p v-if="subtitle">{{ subtitle }}</p>
        </div>
        <slot name="action" />
      </div>
    </IonToolbar>
  </IonHeader>
</template>

<style scoped>
.mobile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  padding: 8px 16px;
}

.brand {
  color: #55d8df;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

h1 {
  margin: 3px 0 0;
  font-size: 20px;
  font-weight: 700;
}

p {
  margin: 3px 0 0;
  color: #71849a;
  font-size: 10px;
}
</style>

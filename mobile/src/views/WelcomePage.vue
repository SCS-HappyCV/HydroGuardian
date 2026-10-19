<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  IonButton,
  IonContent,
  IonIcon,
  IonPage,
  IonSpinner,
} from '@ionic/vue'
import {
  analyticsOutline,
  chevronForwardOutline,
  layersOutline,
  shieldCheckmarkOutline,
} from 'ionicons/icons'
import { primaryFieldUser } from '@/domain/user'
import { useSessionStore } from '@/stores/session'

const router = useRouter()
const route = useRoute()
const session = useSessionStore()
const entering = ref(false)

async function enterWorkspace() {
  entering.value = true
  await session.enter()
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/tabs/tasks'
  await router.replace(redirect)
  entering.value = false
}
</script>

<template>
  <IonPage>
    <IonContent :fullscreen="true" class="welcome-content">
      <main class="welcome-page">
        <div class="ambient ambient-one" />
        <div class="ambient ambient-two" />

        <header>
          <div class="brand-mark">
            <span class="brand-ripple" />
            <IonIcon :icon="layersOutline" />
          </div>
          <div>
            <span>HYDROGUARDIAN</span>
            <strong>水利智巡</strong>
          </div>
        </header>

        <section class="welcome-copy">
          <span class="eyebrow">AI 驱动的水利风险闭环</span>
          <h1>让每一次现场核查<br><em>都有证据、有闭环</em></h1>
          <p>融合遥感影像、点云几何与时相变化，为现场处置提供可解释的风险判断。</p>
        </section>

        <section class="capability-strip">
          <div><IonIcon :icon="analyticsOutline" /><span>多模态研判</span></div>
          <div><IonIcon :icon="shieldCheckmarkOutline" /><span>证据可追溯</span></div>
          <div><IonIcon :icon="layersOutline" /><span>闭环可复盘</span></div>
        </section>

        <section class="identity-card surface">
          <div class="avatar">{{ primaryFieldUser.name.slice(0, 1) }}</div>
          <div>
            <span>当前身份</span>
            <strong>{{ primaryFieldUser.name }}</strong>
            <p>{{ primaryFieldUser.role }} · {{ primaryFieldUser.region }}</p>
          </div>
          <span class="verified"><IonIcon :icon="shieldCheckmarkOutline" />已授权</span>
        </section>

        <IonButton
          expand="block"
          size="large"
          class="enter-button"
          :disabled="entering"
          @click="enterWorkspace"
        >
          <IonSpinner v-if="entering" name="crescent" />
          <template v-else>
            进入现场工作台
            <IonIcon slot="end" :icon="chevronForwardOutline" />
          </template>
        </IonButton>

        <footer>滨海新区水务巡查中心 · 智能风险处置终端</footer>
      </main>
    </IonContent>
  </IonPage>
</template>

<style scoped>
.welcome-content {
  --background:
    radial-gradient(circle at 75% 8%, rgba(45, 212, 191, 0.18), transparent 27%),
    radial-gradient(circle at 10% 58%, rgba(47, 128, 237, 0.15), transparent 32%),
    #06101d;
}

.welcome-page {
  position: relative;
  display: flex;
  min-height: 100%;
  overflow: hidden;
  flex-direction: column;
  padding: calc(34px + env(safe-area-inset-top)) 22px calc(22px + env(safe-area-inset-bottom));
}

.ambient {
  position: absolute;
  border: 1px solid rgba(85, 216, 223, 0.1);
  border-radius: 50%;
  pointer-events: none;
}

.ambient-one {
  top: 11%;
  right: -115px;
  width: 270px;
  height: 270px;
  box-shadow: 0 0 80px rgba(45, 212, 191, 0.08);
}

.ambient-two {
  top: 18%;
  right: -60px;
  width: 150px;
  height: 150px;
}

header {
  display: flex;
  z-index: 1;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  position: relative;
  display: grid;
  width: 46px;
  height: 46px;
  place-items: center;
  border: 1px solid rgba(85, 216, 223, 0.28);
  border-radius: 15px;
  color: #83edf0;
  background: linear-gradient(145deg, rgba(20, 78, 95, 0.9), rgba(11, 42, 59, 0.95));
  font-size: 22px;
}

.brand-ripple {
  position: absolute;
  inset: -6px;
  border: 1px solid rgba(85, 216, 223, 0.08);
  border-radius: 19px;
}

header div:last-child span,
header div:last-child strong {
  display: block;
}

header div:last-child span {
  color: #55d8df;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

header div:last-child strong {
  margin-top: 3px;
  font-size: 18px;
}

.welcome-copy {
  z-index: 1;
  margin-top: clamp(72px, 13vh, 118px);
}

.welcome-copy h1 {
  margin: 14px 0 0;
  font-size: clamp(31px, 8vw, 42px);
  line-height: 1.28;
  letter-spacing: -0.04em;
}

.welcome-copy em {
  color: #74e4e9;
  font-style: normal;
}

.welcome-copy p {
  max-width: 480px;
  margin: 16px 0 0;
  color: #8296ac;
  font-size: 13px;
  line-height: 1.8;
}

.capability-strip {
  display: grid;
  z-index: 1;
  grid-template-columns: repeat(3, 1fr);
  gap: 7px;
  margin-top: 28px;
}

.capability-strip div {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid rgba(148, 180, 208, 0.1);
  border-radius: 11px;
  padding: 10px 5px;
  color: #9bb0c5;
  background: rgba(10, 25, 41, 0.62);
  font-size: 9px;
}

.capability-strip ion-icon {
  color: #55d8df;
  font-size: 14px;
}

.identity-card {
  display: grid;
  z-index: 1;
  grid-template-columns: 48px 1fr auto;
  align-items: center;
  gap: 11px;
  margin-top: auto;
  padding: 14px;
}

.avatar {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 15px;
  color: #8aebef;
  background: linear-gradient(145deg, #164559, #193a4c);
  font-size: 18px;
  font-weight: 800;
}

.identity-card div:nth-child(2) span,
.identity-card div:nth-child(2) strong,
.identity-card div:nth-child(2) p {
  display: block;
}

.identity-card div:nth-child(2) span {
  color: #71849a;
  font-size: 9px;
}

.identity-card div:nth-child(2) strong {
  margin-top: 3px;
  font-size: 14px;
}

.identity-card div:nth-child(2) p {
  margin: 3px 0 0;
  color: #8296ac;
  font-size: 9px;
}

.verified {
  display: flex;
  align-items: center;
  gap: 3px;
  color: #63e3af;
  font-size: 8px;
}

.enter-button {
  z-index: 1;
  min-height: 52px;
  margin-top: 13px;
  font-size: 13px;
  font-weight: 700;
  --border-radius: 15px;
  --background: linear-gradient(100deg, #2778e7, #22b8c7);
  --box-shadow: 0 15px 35px rgba(39, 120, 231, 0.25);
}

.enter-button ion-spinner {
  width: 20px;
}

footer {
  z-index: 1;
  padding-top: 14px;
  color: #566c82;
  font-size: 8px;
  text-align: center;
}
</style>

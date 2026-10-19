<script setup lang="ts">
import {
  IonBackButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonIcon,
  IonPage,
  IonTitle,
  IonToolbar,
} from '@ionic/vue'
import {
  cameraOutline,
  documentLockOutline,
  folderOpenOutline,
  locationOutline,
  shieldCheckmarkOutline,
} from 'ionicons/icons'

const permissions = [
  {
    icon: cameraOutline,
    title: '相机与图片',
    description: '用于采集处置前后影像，形成现场证据对照。',
  },
  {
    icon: locationOutline,
    title: '精确位置',
    description: '仅在点击定位时获取，用于核验现场作业位置与精度。',
  },
  {
    icon: folderOpenOutline,
    title: '应用文件',
    description: '现场照片保存在应用私有目录，其他应用无法直接读取。',
  },
]
</script>

<template>
  <IonPage>
    <IonHeader class="ion-no-border">
      <IonToolbar>
        <IonButtons slot="start">
          <IonBackButton default-href="/tabs/profile" text="" />
        </IonButtons>
        <IonTitle>权限与数据安全</IonTitle>
      </IonToolbar>
    </IonHeader>
    <IonContent>
      <main class="page-shell privacy-page">
        <section class="security-hero surface">
          <div><IonIcon :icon="shieldCheckmarkOutline" /></div>
          <h1>现场证据全程受控</h1>
          <p>权限按业务动作申请，照片、定位和处置记录仅用于水利风险工单闭环。</p>
        </section>

        <section class="permission-list surface">
          <article v-for="item in permissions" :key="item.title">
            <span><IonIcon :icon="item.icon" /></span>
            <div><strong>{{ item.title }}</strong><p>{{ item.description }}</p></div>
          </article>
        </section>

        <section class="retention surface">
          <div><IonIcon :icon="documentLockOutline" /></div>
          <div>
            <strong>数据保留说明</strong>
            <p>尚未提交的现场草稿会持续保存，防止意外退出造成证据丢失。使用“恢复初始任务数据”可以清除现场草稿、证据文件和提交记录。</p>
          </div>
        </section>
      </main>
    </IonContent>
  </IonPage>
</template>

<style scoped>
.privacy-page { display: grid; gap: 14px; }
.security-hero { padding: 25px 20px; text-align: center; }
.security-hero > div { display: grid; width: 58px; height: 58px; margin: 0 auto; place-items: center; border-radius: 18px; color: #63e3af; background: rgba(57,201,138,.09); font-size: 30px; }
.security-hero h1 { margin: 13px 0 0; font-size: 17px; }
.security-hero p { margin: 7px auto 0; max-width: 330px; color: #8296ac; font-size: 9px; line-height: 1.7; }
.permission-list { padding: 0 14px; }
.permission-list article { display: grid; grid-template-columns: 40px 1fr; align-items: center; gap: 11px; padding: 14px 0; }
.permission-list article + article { border-top: 1px solid rgba(148,180,208,.08); }
.permission-list article > span { display: grid; width: 40px; height: 40px; place-items: center; border-radius: 12px; color: #55d8df; background: rgba(45,212,191,.08); font-size: 20px; }
.permission-list strong { font-size: 11px; }
.permission-list p, .retention p { margin: 4px 0 0; color: #71849a; font-size: 9px; line-height: 1.6; }
.retention { display: grid; grid-template-columns: 34px 1fr; gap: 9px; padding: 14px; }
.retention > div:first-child { color: #b8adff; font-size: 22px; }
.retention strong { font-size: 11px; }
</style>

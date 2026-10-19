# HydroGuardian 水利智巡移动端

面向现场巡查与风险处置人员的 Ionic Vue 应用。默认连接 Agent 控制面的真实工单与资产服务，同时保留设备内任务缓存、现场草稿和失败重试记录。

## 本地运行

```bash
pnpm install
pnpm dev
```

## 质量检查

```bash
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

也可以运行 `pnpm check` 一次完成全部检查。

复制 `.env.example` 后可通过 `VITE_DATA_MODE` 切换数据来源，通过
`VITE_API_BASE_URL` 配置 Agent 控制面地址。Android 真机请求使用 Capacitor 原生 HTTP 通道，当前联调地址为 `http://172.16.224.4:18080`。

指定工单支持以下应用深链：

```text
hydroguardian://task/wo-2001
```

现场处置支持：

- 相机拍摄或相册选择；
- 影像写入应用私有文件目录；
- GPS 高精度定位及权限处理；
- 处置说明自动保存和草稿恢复；
- 提交记录、连接状态与失败重试。
- 真实工单列表、接单和开始处置状态同步；
- 处置前后影像预签名上传与 Artifact 登记；
- 现场说明、定位和证据提交人工复核；
- 后端 Agent 证据缩略图展示。

## Android 工程

```bash
pnpm exec cap add android
pnpm cap:sync
pnpm cap:open
```

构建 Android 安装包前，需要在本机配置 Android Studio、Android SDK 以及 `ANDROID_HOME`。

## 比赛构建

Android Studio 中选择 `release` 构建变体，或在 `android/` 目录运行：

```bash
gradlew.bat assembleRelease
```

产物位于 `android/app/build/outputs/apk/release/app-release.apk`。该 Release
构建使用本机 Debug 证书签名，适合比赛现场安装，不用于应用商店发布。

完整演示流程见 `COMPETITION_DEMO_GUIDE.md`。

import { Camera } from '@capacitor/camera'
import { Directory, Encoding, Filesystem } from '@capacitor/filesystem'
import { Geolocation } from '@capacitor/geolocation'
import { Network } from '@capacitor/network'

export type ReadinessState = 'ready' | 'prompt' | 'attention'

export interface ReadinessItem {
  id: 'camera' | 'location' | 'storage' | 'network'
  label: string
  detail: string
  state: ReadinessState
}

const CHECK_FILE = 'hydroguardian/device-check.txt'

export const deviceReadinessService = {
  async check(): Promise<ReadinessItem[]> {
    const results = await Promise.allSettled([
      Camera.checkPermissions(),
      Geolocation.checkPermissions(),
      (async () => {
        await Filesystem.writeFile({
          path: CHECK_FILE,
          directory: Directory.Cache,
          data: 'ready',
          encoding: Encoding.UTF8,
          recursive: true,
        })
        await Filesystem.deleteFile({ path: CHECK_FILE, directory: Directory.Cache })
        return true
      })(),
      Network.getStatus(),
    ])

    const cameraResult = results[0]
    const locationResult = results[1]
    const storageResult = results[2]
    const networkResult = results[3]

    const cameraState = cameraResult.status === 'fulfilled'
      ? cameraResult.value.camera
      : 'denied'
    const locationState = locationResult.status === 'fulfilled'
      ? locationResult.value.location
      : 'denied'
    const connected = networkResult.status === 'fulfilled' && networkResult.value.connected

    return [
      {
        id: 'camera',
        label: '影像采集',
        detail: cameraState === 'denied' ? '相机权限被拒绝，请在系统设置中开启' : cameraState === 'granted' ? '相机和图片选择可用' : '首次拍摄时将请求使用权限',
        state: cameraState === 'denied' ? 'attention' : cameraState === 'granted' ? 'ready' : 'prompt',
      },
      {
        id: 'location',
        label: '现场定位',
        detail: locationState === 'denied' ? '定位权限被拒绝，请在系统设置中开启' : locationState === 'granted' ? '精确位置权限可用' : '首次定位时将请求使用权限',
        state: locationState === 'denied' ? 'attention' : locationState === 'granted' ? 'ready' : 'prompt',
      },
      {
        id: 'storage',
        label: '证据存储',
        detail: storageResult.status === 'fulfilled' ? '应用私有文件目录读写正常' : '文件目录不可用，请重新启动应用',
        state: storageResult.status === 'fulfilled' ? 'ready' : 'attention',
      },
      {
        id: 'network',
        label: '数据连接',
        detail: connected ? '当前连接可用于提交记录' : '连接恢复后可在同步中心重试',
        state: connected ? 'ready' : 'prompt',
      },
    ]
  },
}

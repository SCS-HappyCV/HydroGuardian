// 运行模式工具：统一管理前端 mock/api/hybrid 数据模式，方便比赛现场快速切换。

export type DataMode = 'mock' | 'api' | 'hybrid'

const DATA_MODE_KEY = 'hydroguardian_data_mode'

// 校验字符串是否是前端支持的数据模式。
export function isDataMode(value: string | null | undefined): value is DataMode {
  return value === 'mock' || value === 'api' || value === 'hybrid'
}

// 获取环境变量配置的数据模式；未配置时默认 mock，避免无后端环境打开页面直接失败。
export function getEnvDataMode(): DataMode {
  const mode = import.meta.env.VITE_DATA_MODE
  return isDataMode(mode) ? mode : 'mock'
}

// 从 localStorage 读取用户最近选择的数据模式。
export function loadPersistedDataMode(): DataMode | null {
  if (typeof localStorage === 'undefined') return null
  const value = localStorage.getItem(DATA_MODE_KEY)
  return isDataMode(value) ? value : null
}

// 保存用户选择的数据模式，便于刷新页面后继续联调。
export function savePersistedDataMode(mode: DataMode): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(DATA_MODE_KEY, mode)
}

// 获取当前默认数据模式，优先使用用户本地选择，其次使用环境变量。
export function getDefaultDataMode(): DataMode {
  return loadPersistedDataMode() ?? getEnvDataMode()
}

// 判断当前模式是否会尝试真实 API。
export function shouldUseApi(mode: DataMode): boolean {
  return mode === 'api' || mode === 'hybrid'
}

// 判断当前模式是否允许在 API 失败后回退 mock。
export function canFallbackToMock(mode: DataMode): boolean {
  return mode === 'hybrid'
}

type DataMode = 'local' | 'remote'

function resolveDataMode(value: string | undefined): DataMode {
  return value === 'local' ? 'local' : 'remote'
}

export const runtimeConfig = Object.freeze({
  dataMode: import.meta.env.MODE === 'test' ? 'local' : resolveDataMode(import.meta.env.VITE_DATA_MODE),
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL || 'http://172.16.224.4:18080').replace(/\/$/, ''),
})

/// <reference types="astro/client" />
/// <reference types="@astrojs/vue/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_REMOTE_AGENT_BASE_URL?: string
  readonly VITE_DATA_MODE?: 'mock' | 'api' | 'hybrid'
  readonly VITE_PRESENTATION_MODE?: 'competition' | 'operations'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

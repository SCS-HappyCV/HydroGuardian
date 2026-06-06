/// <reference types="astro/client" />
/// <reference types="@astrojs/vue/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_DATA_MODE?: 'mock' | 'api' | 'hybrid'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

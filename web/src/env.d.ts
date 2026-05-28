/// <reference types="astro/client" />
/// <reference types="@astrojs/vue/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

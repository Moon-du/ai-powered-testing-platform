/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_DEV_ACTOR_ID?: string
  readonly VITE_DEV_USER_ID?: string
  readonly VITE_DEV_ACTOR_ROLE?: string
  readonly VITE_DEV_TENANT_ID?: string
  readonly VITE_ENABLE_DEV_HEADERS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

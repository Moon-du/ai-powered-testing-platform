import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import type { ApiRequestContext } from '@/api/client'
import type { ProjectRole } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  // Intentionally memory-only. OIDC integrations can set this after a PKCE exchange;
  // no token or developer identity is persisted in browser storage.
  const accessToken = ref<string | null>(null)
  const userId = ref(
    import.meta.env.VITE_DEV_USER_ID ??
      import.meta.env.VITE_DEV_ACTOR_ID ??
      'dev-user',
  )
  const actorRole = ref<ProjectRole>(
    (import.meta.env.VITE_DEV_ACTOR_ROLE as ProjectRole | undefined) ?? 'OWNER',
  )
  const tenantId = ref(
    import.meta.env.VITE_DEV_TENANT_ID ?? 'demo-tenant',
  )

  const displayRole = computed(() => actorRole.value.replaceAll('_', ' '))

  function setAccessToken(token: string | null): void {
    accessToken.value = token
  }

  function clearSession(): void {
    accessToken.value = null
  }

  function requestContext(): ApiRequestContext {
    return {
      accessToken: accessToken.value,
      userId: userId.value,
      actorRole: actorRole.value,
      tenantId: tenantId.value,
    }
  }

  return {
    accessToken,
    userId,
    actorRole,
    tenantId,
    displayRole,
    setAccessToken,
    clearSession,
    requestContext,
  }
})

import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from '@/stores/auth'

describe('auth store', () => {
  it('uses the backend OWNER role as the development default', () => {
    setActivePinia(createPinia())

    const auth = useAuthStore()

    expect(auth.actorRole).toBe('OWNER')
    expect(auth.requestContext().actorRole).toBe('OWNER')
  })
})

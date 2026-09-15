import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import { createPinia } from 'pinia'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import App from '@/App.vue'
import { configureApiRequestContext } from '@/api/client'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import 'ant-design-vue/dist/reset.css'
import '@/styles.css'

const app = createApp(App)
const pinia = createPinia()
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

app.use(pinia)
const authStore = useAuthStore(pinia)
configureApiRequestContext(() => authStore.requestContext())

app.use(router)
app.use(Antd)
app.use(VueQueryPlugin, { queryClient })
app.mount('#app')

import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { useBranding } from './stores/branding'

const app = createApp(App)

app.use(router)
app.use(i18n)

app.mount('#app')

// Apply branding after mount (non-blocking, public endpoint)
useBranding().applyBranding().catch(() => {})

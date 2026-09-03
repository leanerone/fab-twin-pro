import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import { seedIfEmpty } from './data/seed'

// 首次运行注入假数据
seedIfEmpty()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

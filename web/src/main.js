import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './styles/main.css'
import { startKeepalive } from './lib/keepalive'

startKeepalive()

createApp(App).use(router).mount('#app')

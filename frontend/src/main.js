/**
 * AI 智能公文创作 — Vue 3 独立前端应用入口
 *
 * 启动方式：
 *   cd frontend
 *   npm run serve            # → http://localhost:8081
 *
 * 依赖的后端服务：
 *   cd ..
 *   python scripts/run_api.py   # → http://localhost:8000
 */
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import Antd from 'ant-design-vue';
import 'ant-design-vue/dist/antd.css';
import App from './App.vue';

const app = createApp(App);
app.use(createPinia());
app.use(Antd);
app.mount('#app');

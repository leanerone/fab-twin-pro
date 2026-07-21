import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// Vite 配置：dev server 端口 5173，代理 /api 和 /ws 到后端
// preview 模式（vite preview）也需要相同的代理配置
const proxyConfig = {
  '/api': {
    target: 'http://localhost:8002',
    changeOrigin: true,
  },
  '/ws': {
    target: 'ws://localhost:8002',
    ws: true,
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: proxyConfig,
  },
  preview: {
    port: 5173,
    host: true,
    proxy: proxyConfig,
  },
})

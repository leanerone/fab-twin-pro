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
  '/uploads': {
    target: 'http://localhost:8002',
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
  // test31 构建优化：
  // - manualChunks：three（约600KB）/vue 全家桶拆独立长缓存 chunk——业务代码
  //   改动不再使整个大包缓存失效
  // - drop console：生产构建剔除 console（路由守卫/高频事件流的日志序列化开销）
  esbuild: {
    drop: ['console', 'debugger'],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
          vue: ['vue', 'vue-router', 'pinia'],
        },
      },
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

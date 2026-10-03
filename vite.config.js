import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 前端配置集中在这里：端口 / 代理目标都从一处控制。
// 后端地址与 config/settings.py 中的 BACKEND_HOST/BACKEND_PORT 保持一致。
const BACKEND = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
    // 把 /api 转发到后端，前端代码里只写相对路径 /api/xxx，
    // 这样以后改后端端口只改这一处 + settings.py，前端组件一行都不用动。
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})

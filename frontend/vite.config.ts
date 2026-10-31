import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

function localPort(value: string | undefined, fallback: number) {
  if (value === undefined) return fallback
  if (!/^\d+$/.test(value)) throw new Error('로컬 포트는 정수여야 합니다.')
  const port = Number(value)
  if (!Number.isSafeInteger(port) || port < 1024 || port > 65535) throw new Error('로컬 포트는 1024~65535 범위여야 합니다.')
  return port
}

const apiPort = localPort(process.env.ONEUL_API_PORT, 18080)
const frontendPort = localPort(process.env.ONEUL_FRONTEND_PORT, 15173)
if (apiPort === frontendPort) throw new Error('화면과 API의 포트는 서로 달라야 합니다.')

export default defineConfig({
  plugins: [react()],
  cacheDir: '../.local/vite-cache',
  server: {
    host: '127.0.0.1',
    port: frontendPort,
    strictPort: true,
    proxy: {
      '/api': `http://127.0.0.1:${apiPort}`,
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 15174,
    strictPort: true,
  },
})

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import fs from 'node:fs'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  const rootEnvFile = fileURLToPath(new URL('../.env', import.meta.url))
  // 手动读取根目录 .env（AMAP_KEY 等不满足 VITE_ 前缀，loadEnv 不会加载）
  let rootEnv: Record<string, string> = {}
  try {
    const content = fs.readFileSync(rootEnvFile, 'utf-8')
    for (const line of content.split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/)
      if (m && !line.trim().startsWith('#')) rootEnv[m[1]] = m[2].replace(/^["']|["']$/g, '')
    }
  } catch {
    /* .env 不存在则忽略 */
  }
  const env = { ...rootEnv, ...loadEnv(mode, process.cwd()) }

  return {
    // 部署在工作台子路径 /map/ 下（由 8080 网关分发）
    base: '/map/',
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true
        },
        '/ws': {
          target: 'ws://localhost:8000',
          ws: true
        }
      }
    },
    // 高德 Key 通过构建变量注入 index.html
    define: {
      'import.meta.env.VITE_AMAP_KEY': JSON.stringify(
        env.VITE_AMAP_KEY || env.AMAP_KEY || process.env.VITE_AMAP_KEY || process.env.AMAP_KEY || ''
      )
    }
  }
})
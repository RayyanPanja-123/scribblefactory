import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const proxy = { '/api': 'http://127.0.0.1:8765' }

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: { proxy },
  preview: { proxy },
})

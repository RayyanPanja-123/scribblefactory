/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// SCRIBBLE_API: where /api goes (scripts/screenshots.mjs points it at its own API)
declare const process: { env: Record<string, string | undefined> } // no @types/node needed for one env var
const proxy = { '/api': process.env.SCRIBBLE_API ?? 'http://127.0.0.1:8765' }

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  // fs.allow: the prop preview imports the engine's own drawing code from ../engine/page
  server: { proxy, fs: { allow: ['..'] } },
  preview: { proxy },
  test: { maxWorkers: 2 }, // vitest's default (cores - 1) makes the PC unusable while it runs
})

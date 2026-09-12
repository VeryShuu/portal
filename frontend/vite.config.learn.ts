import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import { fileURLToPath, URL } from 'node:url'

/**
 * Отдельная сборка learn-контура (ADR-051, ТЗ §9). Сознательно НЕ наследует
 * vite.config.ts: глубокий merge притащил бы портал-чанки (editor/tiptap),
 * а критерий приёмки — «в статике публичного контура нет чанков портальных
 * страниц» (проверяется npm run check:learn-static).
 *
 * VITE_LEARN_CONTOUR включается через define: api/index на 401 не ходит в
 * портальный silent-refresh и не редиректит на SSO (на learn-домене его нет).
 */
export default defineConfig({
  plugins: [
    vue(),
    VueI18nPlugin({
      include: [fileURLToPath(new URL('./src/i18n/*.json', import.meta.url))],
      runtimeOnly: true,
      compositionOnly: true,
      fullInstall: false,
      strictMessage: false,
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  define: {
    'import.meta.env.VITE_LEARN_CONTOUR': JSON.stringify('1'),
  },
  server: {
    port: 5174,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: false,
      },
    },
  },
  preview: {
    port: Number(process.env.LEARN_PREVIEW_PORT ?? 4174),
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        // changeOrigin=false: Host остаётся learn-origin — и бэкендовский
        // CSRF host-fallback, и seeding learning_base_url работают.
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist-learn',
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: false,
    rollupOptions: {
      input: {
        // ключ "index" → в outDir ляжет index.html (nginx serve index + vite preview)
        index: fileURLToPath(new URL('./learn.html', import.meta.url)),
      },
      output: {
        manualChunks: {
          // Только общий рантайм UI; никакого tiptap/editor из портал-конфига.
          vendor: ['vue', 'vue-router'],
          naive: ['naive-ui'],
        },
      },
    },
  },
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import { fileURLToPath, URL } from 'node:url'
import { visualizer } from 'rollup-plugin-visualizer'

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
    process.env.ANALYZE === 'true'
      ? visualizer({
          filename: 'dist/stats.html',
          open: true,
          gzipSize: true,
          brotliSize: true,
        })
      : null,
  ].filter(Boolean),
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Vite блокирует запросы с Host, отсутствующего в белом списке
    // («Blocked request»). В dev хост задаётся через Admin UI (system.json →
    // portal_base_url) и может быть любым, поэтому по умолчанию разрешаем все
    // хосты — это безопасно: dev-сервер сидит за nginx (CIDR + TLS).
    // При желании ограничить — задать VITE_ALLOWED_HOSTS=host1,host2,...
    allowedHosts: process.env.VITE_ALLOWED_HOSTS
      ? process.env.VITE_ALLOWED_HOSTS.split(',').map((h) => h.trim()).filter(Boolean)
      : true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ready': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['vue', 'vue-router', 'pinia'],
          'naive': ['naive-ui'],
          'editor': [
            '@tiptap/vue-3',
            '@tiptap/starter-kit',
            '@tiptap/extension-link',
            '@tiptap/extension-placeholder',
            '@tiptap/extension-table',
            '@tiptap/extension-table-cell',
            '@tiptap/extension-table-header',
            '@tiptap/extension-table-row',
            'tiptap-markdown',
            'markdown-it',
          ],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.{test,spec}.ts'],
    // Тяжёлые page-mount-тесты (KbArticlePage, NewsFormPage, FilesPage …) под
    // v8-coverage идут 1-2.5с на 8 ядрах; на нагруженном self-hosted CI-раннере
    // (shared CPU + concurrent jobs + jsdom) — до ~3x медленнее → дефолтные
    // 5000ms срывались в flaky-таймаут (см. ci.yml run #87: 2 теста упёрлись в
    // 5с, заблокировав publish-images). 15000ms ≈ 6x самого медленного легитимного
    // теста: убирает CI-флуктуацию и всё ещё ловит реальные зависания.
    // Замер: `npx vitest run --coverage --reporter=json` → top: files-page 2.5с,
    // news-form 1.9с, kb-article 1.6с.
    testTimeout: 15000,
    // На shared self-hosted runner одновременно стартуют backend, integration,
    // build и service jobs. Автовыбор Vitest по числу host CPU запускал слишком
    // много jsdom workers: шесть независимых файлов стабильно упирались в 15s,
    // хотя те же тесты по отдельности занимают миллисекунды. Ограничиваем только
    // CI; локально сохраняем автоматический параллелизм.
    maxWorkers: process.env.CI ? 4 : undefined,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: [
        'src/api/types.gen.d.ts',
        'src/main.ts',
        'src/learn/main.ts', // bootstrap-точка входа learn-сборки (аналог src/main.ts)
        'src/i18n/**',
        'src/styles/**',
      ],
      reporter: ['text', 'html', 'lcov', 'cobertura'],
      reportsDirectory: 'coverage',
      thresholds: {
        // Фактическое покрытие (замер 2026-07-20, итерация 17):
        // lines 66.67% / branches 60.58% / funcs 54.26% / stmts 68.31%.
        // Пороги установлены на 2% ниже факта — защита от регресса без ложных
        // срабатываний на CI-флуктуациях. Поднимать до фактических значений
        // только осознанно, после стабилизации покрытия.
        lines: 65,
        functions: 52,
        branches: 59,
        statements: 66,
      },
    },
  },
})

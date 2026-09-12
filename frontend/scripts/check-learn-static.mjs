#!/usr/bin/env node
/**
 * Критерий приёмки learn-контура (ТЗ §9, ADR-051): в статике публичного
 * контура dist-learn/ нет чанков портальных страниц.
 *
 * Проверяем два среза:
 *   1. имена файлов — чанк, названный в честь портал-модуля (lazy-import
 *      сохраняет имя файла), не должен существовать;
 *   2. содержимое бандлов — имена портал-страниц не встречаются даже в
 *      строках (re-export/манифест).
 *
 * Запуск: npm run build:learn && npm run check:learn-static
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const DIST = 'dist-learn'

// Имена портал-страниц/модулей, которых в learn-бандле быть не может.
// Достаточно характерных подстрок имён чанков (rollup называет чанки по файлу).
const FORBIDDEN = [
  // страницы портала
  'AdminPage', 'NewsListPage', 'NewsFormPage', 'KbListPage', 'KbArticlePage',
  'KbArticleFormPage', 'KbTrashPage', 'FilesPage', 'LinksAndBookmarksPage',
  'StaffDirectoryPage', 'PhotosIndexPage', 'MySharesPage', 'MeetingsPage',
  'SignaturePage', 'HelpdeskAgentInboxPage', 'HelpdeskAgentTicketDetailPage',
  'HelpdeskArchivePage', 'HelpdeskMyTicketsPage', 'AdminPage', 'TrashPage',
  'UserProfileView', 'HomePage', 'AuthLocalPage', 'AuthCallbackPage',
  'LearningAdminPage',
  // портал-инфраструктура
  'AppLayout', 'AppHeader', 'AppSider', 'useAppMenu', 'GlobalSearch',
  // тяжёлые портал-зависимости, которых в учебном контуре нет
  'tiptap', 'TipTap',
  // markdown-it в learn-бандле ДОПУСТИМ с 2026-08-31: rich-описание курса
  // рендерится тем же конвейером, что новости (Markdown → DOMPurify);
  // портал-страниц это по-прежнему не приносит.
]

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) yield* walk(p)
    else yield p
  }
}

let files
try {
  files = [...walk(DIST)]
} catch {
  console.error(`✗ ${DIST}/ не найден — сначала npm run build:learn`)
  process.exit(1)
}
if (files.length === 0) {
  console.error(`✗ ${DIST}/ пуст`)
  process.exit(1)
}

const failures = []
for (const file of files) {
  for (const token of FORBIDDEN) {
    if (file.includes(token)) {
      failures.push(`имя файла содержит «${token}»: ${file}`)
    }
  }
}

// Содержимое: только .js бандлы (html/css не содержат имён модулей).
const jsFiles = files.filter((f) => f.endsWith('.js'))
for (const file of jsFiles) {
  const content = readFileSync(file, 'utf8')
  for (const token of FORBIDDEN) {
    if (content.includes(token)) {
      failures.push(`«${token}» найден в содержимом ${file}`)
    }
  }
}

// Sanity: learn-точка входа обязана существовать.
const hasEntry = files.some((f) => f.endsWith('.html') && readFileSync(f, 'utf8').includes('learn-app'))
if (!hasEntry) {
  failures.push('не найден learn html-entry (div#learn-app)')
}

if (failures.length > 0) {
  console.error('✗ check-learn-static: портал-артефакты в learn-сборке:')
  for (const f of [...new Set(failures)].slice(0, 30)) console.error('  -', f)
  process.exit(1)
}

console.log(`✓ check-learn-static: ${files.length} файлов, портал-чанков нет`)

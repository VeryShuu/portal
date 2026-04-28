<template>
  <n-modal
    :show="show"
    preset="card"
    :mask-closable="true"
    :close-on-esc="true"
    :bordered="false"
    :segmented="false"
    class="gs-modal"
    :style="{ width: '640px', maxWidth: '94vw' }"
    :auto-focus="false"
    display-directive="if"
    @update:show="$emit('update:show', $event)"
    @after-enter="focusInput"
  >
    <div class="gs">
      <div class="gs__input-wrap">
        <n-icon size="18" class="gs__icon"><SearchOutline /></n-icon>
        <input
          ref="inputEl"
          v-model="query"
          type="text"
          class="gs__input"
          :placeholder="t('search.placeholder')"
          :aria-label="t('search.placeholder')"
          @keydown.down.prevent="move(1)"
          @keydown.up.prevent="move(-1)"
          @keydown.enter.prevent="pickActive"
          @keydown.esc.prevent="$emit('update:show', false)"
        />
        <kbd class="gs__esc">Esc</kbd>
      </div>

      <div class="gs__results" role="listbox">
        <template v-if="isCommandMode">
          <div class="gs__group">
            <div class="gs__group-title">{{ t('search.commands.title') }}</div>
            <button
              v-for="(cmd, i) in filteredCommands"
              :key="cmd.id"
              type="button"
              class="gs__item"
              :class="{ 'gs__item--active': activeIndex === i }"
              @mouseenter="activeIndex = i"
              @click="runCommand(cmd)"
            >
              <n-icon size="16" class="gs__item-icon"><component :is="cmd.icon" /></n-icon>
              <span class="gs__item-title">{{ cmd.label }}</span>
              <kbd v-if="cmd.shortcut" class="gs__item-kbd">{{ cmd.shortcut }}</kbd>
            </button>
            <div v-if="!filteredCommands.length" class="gs__hint">
              <div>{{ t('search.noResults') }}</div>
            </div>
          </div>
        </template>

        <template v-else-if="!query.trim()">
          <div v-if="recent.length" class="gs__group">
            <div class="gs__group-title">{{ t('search.recent') }}</div>
            <button
              v-for="(q, i) in recent"
              :key="`r-${i}`"
              type="button"
              class="gs__item"
              :class="{ 'gs__item--active': activeIndex === i }"
              @mouseenter="activeIndex = i"
              @click="pickRecent(q)"
            >
              <n-icon size="16" class="gs__item-icon"><TimeOutline /></n-icon>
              <span class="gs__item-title">{{ q }}</span>
            </button>
          </div>
          <div v-else class="gs__hint">
            <n-icon size="28"><SearchOutline /></n-icon>
            <div>{{ t('search.hint') }}</div>
            <div class="gs__hint-cmd">{{ t('search.commandHint') }}</div>
          </div>
        </template>

        <template v-else>
          <div v-if="newsResults.length" class="gs__group">
            <div class="gs__group-title">{{ t('nav.news') }}</div>
            <button
              v-for="(n, i) in newsResults"
              :key="n.id"
              type="button"
              class="gs__item"
              :class="{ 'gs__item--active': activeIndex === offsetNews + i }"
              @mouseenter="activeIndex = offsetNews + i"
              @click="pickNews(n)"
            >
              <n-icon size="16" class="gs__item-icon"><NewspaperOutline /></n-icon>
              <span class="gs__item-title">{{ n.title }}</span>
              <span class="gs__item-meta">{{ formatDate(n.published_at ?? n.created_at) }}</span>
            </button>
          </div>

          <div v-if="linkResults.length" class="gs__group">
            <div class="gs__group-title">{{ t('nav.links') }}</div>
            <button
              v-for="(l, i) in linkResults"
              :key="l.id"
              type="button"
              class="gs__item"
              :class="{ 'gs__item--active': activeIndex === offsetLinks + i }"
              @mouseenter="activeIndex = offsetLinks + i"
              @click="pickLink(l)"
            >
              <n-icon size="16" class="gs__item-icon"><GridOutline /></n-icon>
              <span class="gs__item-title">{{ l.title }}</span>
              <span v-if="l.category" class="gs__item-meta">{{ l.category }}</span>
            </button>
          </div>

          <div v-if="bookmarkResults.length" class="gs__group">
            <div class="gs__group-title">{{ t('nav.bookmarks') }}</div>
            <button
              v-for="(b, i) in bookmarkResults"
              :key="b.id"
              type="button"
              class="gs__item"
              :class="{ 'gs__item--active': activeIndex === offsetBookmarks + i }"
              @mouseenter="activeIndex = offsetBookmarks + i"
              @click="pickBookmark(b)"
            >
              <n-icon size="16" class="gs__item-icon"><BookmarkOutline /></n-icon>
              <span class="gs__item-title">{{ b.title }}</span>
              <span class="gs__item-meta">{{ hostOf(b.url) }}</span>
            </button>
          </div>

          <div v-if="kbResults.length" class="gs__group">
            <div class="gs__group-title">{{ t('nav.kb') }}</div>
            <button
              v-for="(a, i) in kbResults"
              :key="a.id"
              type="button"
              class="gs__item"
              :class="{ 'gs__item--active': activeIndex === offsetKb + i }"
              @mouseenter="activeIndex = offsetKb + i"
              @click="pickKb(a)"
            >
              <n-icon size="16" class="gs__item-icon"><DocumentTextOutline /></n-icon>
              <span class="gs__item-title">{{ a.title }}</span>
              <span v-if="a.snippet" class="gs__item-meta">{{ a.snippet?.slice(0, 60) }}</span>
            </button>
          </div>

          <div v-if="loading" class="gs__hint">
            <div class="gs__spinner" />
            <div>{{ t('search.loading') }}</div>
          </div>
          <div
            v-else-if="!newsResults.length && !linkResults.length && !bookmarkResults.length && !kbResults.length"
            class="gs__hint"
          >
            <n-icon size="28"><AlertCircleOutline /></n-icon>
            <div>{{ t('search.noResults') }}</div>
          </div>
        </template>
      </div>

      <div class="gs__footer">
        <span><kbd>↑</kbd><kbd>↓</kbd> {{ t('search.nav') }}</span>
        <span><kbd>Enter</kbd> {{ t('search.open') }}</span>
        <span><kbd>Esc</kbd> {{ t('search.close') }}</span>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NModal, NIcon } from 'naive-ui'
import {
  SearchOutline, TimeOutline, NewspaperOutline, GridOutline,
  BookmarkOutline, AlertCircleOutline, DocumentTextOutline,
  PersonOutline, SettingsOutline, LogOutOutline, ColorPaletteOutline,
  BookOutline, HomeOutline,
} from '@vicons/ionicons5'
import { fetchNewsList, type News } from '../api/news'
import { useLinksStore } from '../stores/links'
import type { ServiceLink, Bookmark } from '../api/links'
import { globalSearch, type SearchResultItem } from '../api/kb'
import { isSafeHttpUrl } from '../utils/url'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [v: boolean] }>()

const { t, locale } = useI18n()
const router = useRouter()
const linksStore = useLinksStore()
const auth = useAuthStore()
const themeStore = useThemeStore()

interface Command {
  id: string
  icon: unknown
  label: string
  shortcut?: string
  action: () => void
}

const isCommandMode = computed(() => query.value.startsWith('>'))
const commandQuery = computed(() => query.value.slice(1).trim().toLowerCase())

const allCommands = computed<Command[]>(() => {
  const cmds: Command[] = [
    { id: 'go-home', icon: HomeOutline, label: t('search.commands.goHome'), action: () => { router.push('/'); close() } },
    { id: 'go-news', icon: NewspaperOutline, label: t('search.commands.goNews'), action: () => { router.push('/news'); close() } },
    { id: 'go-kb', icon: BookOutline, label: t('search.commands.goKb'), action: () => { router.push('/kb'); close() } },
    { id: 'go-profile', icon: PersonOutline, label: t('search.commands.goProfile'), action: () => { router.push('/profile'); close() } },
    { id: 'toggle-theme', icon: ColorPaletteOutline, label: t('search.commands.toggleTheme'), shortcut: t('nav.toggleTheme'), action: () => { themeStore.toggle(); close() } },
    { id: 'logout', icon: LogOutOutline, label: t('search.commands.logout'), action: () => { auth.logout(); close() } },
  ]
  if (auth.isEditor) cmds.splice(1, 0, { id: 'create-news', icon: NewspaperOutline, label: t('search.commands.createNews'), action: () => { router.push('/news/create'); close() } })
  if (auth.isAdmin) cmds.push({ id: 'go-admin', icon: SettingsOutline, label: t('search.commands.goAdmin'), action: () => { router.push('/admin'); close() } })
  return cmds
})

const filteredCommands = computed(() => {
  const q = commandQuery.value
  if (!q) return allCommands.value
  return allCommands.value.filter(c => c.label.toLowerCase().includes(q))
})

function runCommand(cmd: Command) {
  cmd.action()
}

const query = ref('')
const activeIndex = ref(0)
const loading = ref(false)
const newsResults = ref<News[]>([])
const kbResults = ref<SearchResultItem[]>([])
const inputEl = ref<HTMLInputElement | null>(null)

const RECENT_KEY = 'gs-recent'
const recent = ref<string[]>(loadRecent())

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}
function saveRecent(q: string) {
  if (!q.trim()) return
  const list = [q, ...recent.value.filter((x) => x !== q)].slice(0, 8)
  recent.value = list
  localStorage.setItem(RECENT_KEY, JSON.stringify(list))
}

const linkResults = computed<ServiceLink[]>(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return []
  return linksStore.links
    .filter((l) =>
      l.title.toLowerCase().includes(q) ||
      (l.description ?? '').toLowerCase().includes(q) ||
      (l.category ?? '').toLowerCase().includes(q),
    )
    .slice(0, 6)
})
const bookmarkResults = computed<Bookmark[]>(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return []
  return linksStore.bookmarks
    .filter((b) =>
      b.title.toLowerCase().includes(q) ||
      b.url.toLowerCase().includes(q),
    )
    .slice(0, 6)
})

const offsetNews = 0
const offsetLinks = computed(() => newsResults.value.length)
const offsetBookmarks = computed(() => newsResults.value.length + linkResults.value.length)
const offsetKb = computed(() => newsResults.value.length + linkResults.value.length + bookmarkResults.value.length)
const totalCount = computed(() => {
  if (!query.value.trim()) return recent.value.length
  return newsResults.value.length + linkResults.value.length + bookmarkResults.value.length + kbResults.value.length
})

// Debounced news search (P1-29: AbortController cancels stale requests).
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let inflight: AbortController | null = null
watch(query, (q) => {
  activeIndex.value = 0
  if (debounceTimer) clearTimeout(debounceTimer)
  if (inflight) {
    inflight.abort()
    inflight = null
  }
  if (!q.trim()) {
    newsResults.value = []
    kbResults.value = []
    loading.value = false
    return
  }
  loading.value = true
  debounceTimer = setTimeout(async () => {
    const ctrl = new AbortController()
    inflight = ctrl
    try {
      const [newsRes, kbRes] = await Promise.all([
        fetchNewsList(
          { page: 1, page_size: 20, status: 'published' },
          { signal: ctrl.signal },
        ),
        globalSearch(q, { limit: 6 }),
      ])
      if (ctrl.signal.aborted) return
      const lq = q.toLowerCase()
      newsResults.value = newsRes.items
        .filter((n) => n.title.toLowerCase().includes(lq) || n.body.toLowerCase().includes(lq))
        .slice(0, 6)
      kbResults.value = kbRes.items.filter((r) => r.type === 'article').slice(0, 5)
    } catch (err) {
      const name = (err as { name?: string })?.name
      if (name === 'AbortError' || ctrl.signal.aborted) return
      // eslint-disable-next-line no-console
      console.warn('[GlobalSearch] search failed', err)
    } finally {
      if (inflight === ctrl) {
        inflight = null
        loading.value = false
      }
    }
  }, 250)
})

watch(() => props.show, (v) => {
  if (v) {
    query.value = ''
    activeIndex.value = 0
    if (linksStore.links.length === 0) linksStore.loadLinks()
    if (linksStore.bookmarks.length === 0) linksStore.loadBookmarks()
  }
})

function focusInput() {
  nextTick(() => inputEl.value?.focus())
}

function move(delta: number) {
  if (isCommandMode.value) {
    const n = filteredCommands.value.length
    if (n === 0) return
    activeIndex.value = (activeIndex.value + delta + n) % n
    return
  }
  const n = totalCount.value
  if (n === 0) return
  activeIndex.value = (activeIndex.value + delta + n) % n
}

function pickActive() {
  if (isCommandMode.value) {
    const cmd = filteredCommands.value[activeIndex.value]
    if (cmd) runCommand(cmd)
    return
  }
  const q = query.value.trim()
  if (!q) {
    const r = recent.value[activeIndex.value]
    if (r) pickRecent(r)
    return
  }
  const idx = activeIndex.value
  if (idx < offsetLinks.value) {
    const n = newsResults.value[idx]
    if (n) pickNews(n)
  } else if (idx < offsetBookmarks.value) {
    const l = linkResults.value[idx - offsetLinks.value]
    if (l) pickLink(l)
  } else if (idx < offsetKb.value) {
    const b = bookmarkResults.value[idx - offsetBookmarks.value]
    if (b) pickBookmark(b)
  } else {
    const a = kbResults.value[idx - offsetKb.value]
    if (a) pickKb(a)
  }
}

function close() {
  emit('update:show', false)
}
function pickRecent(q: string) {
  query.value = q
  activeIndex.value = 0
}
function pickNews(n: News) {
  saveRecent(query.value)
  router.push(`/news/${n.id}`)
  close()
}
function pickLink(l: ServiceLink) {
  saveRecent(query.value)
  linksStore.openLink(l)
  close()
}
function pickBookmark(b: Bookmark) {
  if (!isSafeHttpUrl(b.url)) return
  saveRecent(query.value)
  window.open(b.url, '_blank', 'noopener')
  close()
}
function pickKb(a: SearchResultItem) {
  saveRecent(query.value)
  router.push(a.url)
  close()
}

function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return ''
  }
}
function formatDate(d: string): string {
  const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(d).toLocaleDateString(lang, { day: 'numeric', month: 'short' })
}
</script>

<style scoped>
.gs-modal :deep(.n-card) {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  padding: 0;
}
.gs-modal :deep(.n-card__content) { padding: 0; }

.gs {
  display: flex;
  flex-direction: column;
  max-height: 70vh;
}

.gs__input-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--color-border);
}
.gs__icon { color: var(--color-text-muted); }
.gs__input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 16px;
  font-family: inherit;
  color: var(--color-text);
}
.gs__input::placeholder { color: var(--color-text-subtle); }
.gs__esc {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  padding: 3px 7px;
  border-radius: 4px;
  background: var(--color-bg-muted);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.gs__results {
  flex: 1;
  overflow-y: auto;
  padding: 6px 8px 8px;
  min-height: 120px;
}
.gs__group + .gs__group { margin-top: 6px; }
.gs__group-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  padding: 10px 10px 6px;
}
.gs__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  text-align: left;
  padding: 10px 10px;
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  transition: background var(--t-fast);
}
.gs__item--active,
.gs__item:hover {
  background: var(--color-bg-muted);
}
.gs__item--active {
  background: var(--color-brand-ice);
}
.gs__item-icon { color: var(--color-brand-sky); flex-shrink: 0; }
.gs__item-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gs__item-meta {
  font-size: 12px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.gs__hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: var(--color-text-muted);
  font-size: 13px;
}
.gs__spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-brand-red);
  border-radius: 50%;
  animation: gs-spin 0.8s linear infinite;
}
@keyframes gs-spin {
  to { transform: rotate(360deg); }
}

.gs__footer {
  display: flex;
  gap: 16px;
  padding: 10px 16px;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg);
  font-size: 11px;
  color: var(--color-text-muted);
}
.gs__footer kbd {
  font-family: ui-monospace, monospace;
  font-size: 10px;
  padding: 2px 5px;
  margin-right: 4px;
  border-radius: 3px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text);
}
</style>

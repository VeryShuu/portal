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
          @keydown.esc.prevent="close"
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
              role="option"
              :aria-selected="activeIndex === i"
              class="gs__item"
              :class="{ 'gs__item--active': activeIndex === i }"
              @mouseenter="activeIndex = i"
              @click="cmd.action()"
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
              role="option"
              :aria-selected="activeIndex === i"
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
          <SearchResultGroup
            :title="t('nav.news')"
            :icon="NewspaperOutline"
            :items="newsResults"
            :offset="offsetNews"
            :active-index="activeIndex"
            :get-key="(n: News) => n.id"
            :get-title="(n: News) => n.title"
            :get-meta="(n: News) => formatDate(n.published_at ?? n.created_at)"
            @hover="(i) => activeIndex = i"
            @pick="pickNews"
          />
          <SearchResultGroup
            :title="t('nav.links')"
            :icon="GridOutline"
            :items="linkResults"
            :offset="offsetLinks"
            :active-index="activeIndex"
            :get-key="(l: ServiceLink) => l.id"
            :get-title="(l: ServiceLink) => l.title"
            :get-meta="(l: ServiceLink) => l.category ?? null"
            @hover="(i) => activeIndex = i"
            @pick="pickLink"
          />
          <SearchResultGroup
            :title="t('nav.bookmarks')"
            :icon="BookmarkOutline"
            :items="bookmarkResults"
            :offset="offsetBookmarks"
            :active-index="activeIndex"
            :get-key="(b: Bookmark) => b.id"
            :get-title="(b: Bookmark) => b.title"
            :get-meta="(b: Bookmark) => hostOf(b.url)"
            @hover="(i) => activeIndex = i"
            @pick="pickBookmark"
          />
          <SearchResultGroup
            :title="t('nav.kb')"
            :icon="DocumentTextOutline"
            :items="kbResults"
            :offset="offsetKb"
            :active-index="activeIndex"
            :get-key="(a: SearchResultItem) => a.id"
            :get-title="(a: SearchResultItem) => a.title"
            :get-meta="(a: SearchResultItem) => a.snippet?.slice(0, 60) ?? null"
            @hover="(i) => activeIndex = i"
            @pick="pickKb"
          />
          <SearchResultGroup
            :title="t('users.title')"
            :icon="PersonOutline"
            :items="userResults"
            :offset="offsetUsers"
            :active-index="activeIndex"
            :get-key="(u: UserPublic) => u.id"
            :get-title="(u: UserPublic) => u.full_name"
            :get-meta="(u: UserPublic) => u.position ?? null"
            @hover="(i) => activeIndex = i"
            @pick="pickUser"
          />

          <div v-if="loading" class="gs__hint">
            <div class="gs__spinner" />
            <div>{{ t('search.loading') }}</div>
          </div>
          <div
            v-else-if="!newsResults.length && !linkResults.length && !bookmarkResults.length && !kbResults.length && !userResults.length"
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
  PersonOutline,
} from '@vicons/ionicons5'
import type { News } from '../api/news'
import { useLinksStore } from '../stores/links'
import type { ServiceLink, Bookmark } from '../api/links'
import type { SearchResultItem } from '../api/kb'
import type { UserPublic } from '../api/users'
import { isSafeHttpUrl } from '../utils/url'
import { ROUTES } from '../router'
import { formatDateShort } from '../utils/formatDate'
import SearchResultGroup from './search/SearchResultGroup.vue'
import { useGlobalSearchCommands } from '../composables/useGlobalSearchCommands'
import { useGlobalSearchResults } from '../composables/useGlobalSearchResults'

const RECENT_MAX = 8

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [v: boolean] }>()

const { t, locale } = useI18n()
const router = useRouter()
const linksStore = useLinksStore()

const query = ref('')
const activeIndex = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)

function close() {
  emit('update:show', false)
}

const { isCommandMode, filteredCommands } = useGlobalSearchCommands(query, close)

const {
  loading,
  newsResults,
  linkResults,
  bookmarkResults,
  kbResults,
  userResults,
  ensureCatalogLoaded,
} = useGlobalSearchResults(query)

const RECENT_KEY = 'gs-recent'
const recent = ref<string[]>(loadRecent())

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is string => typeof item === 'string')
  } catch {
    return []
  }
}
function saveRecent(q: string) {
  if (!q.trim()) return
  const list = [q, ...recent.value.filter((x) => x !== q)].slice(0, RECENT_MAX)
  recent.value = list
  localStorage.setItem(RECENT_KEY, JSON.stringify(list))
}

const offsetNews = 0
const offsetLinks = computed(() => newsResults.value.length)
const offsetBookmarks = computed(() => newsResults.value.length + linkResults.value.length)
const offsetKb = computed(() => newsResults.value.length + linkResults.value.length + bookmarkResults.value.length)
const offsetUsers = computed(() => newsResults.value.length + linkResults.value.length + bookmarkResults.value.length + kbResults.value.length)
const totalCount = computed(() => {
  if (!query.value.trim()) return recent.value.length
  return newsResults.value.length + linkResults.value.length + bookmarkResults.value.length + kbResults.value.length + userResults.value.length
})

watch(query, () => {
  activeIndex.value = 0
})

watch(() => props.show, (v) => {
  if (v) {
    query.value = ''
    activeIndex.value = 0
    ensureCatalogLoaded()
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
    if (cmd) cmd.action()
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
  } else if (idx < offsetUsers.value) {
    const a = kbResults.value[idx - offsetKb.value]
    if (a) pickKb(a)
  } else {
    const u = userResults.value[idx - offsetUsers.value]
    if (u) pickUser(u)
  }
}

function pickRecent(q: string) {
  query.value = q
  activeIndex.value = 0
}
function pickNews(n: News) {
  saveRecent(query.value)
  router.push(`${ROUTES.NEWS}/${n.id}`)
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
  window.open(b.url, '_blank', 'noopener,noreferrer')
  close()
}
function isSafeInternalPath(url: string): boolean {
  return url.startsWith('/') && !url.startsWith('//')
}
function pickKb(a: SearchResultItem) {
  saveRecent(query.value)
  if (isSafeInternalPath(a.url)) {
    router.push(a.url)
  }
  close()
}
function pickUser(u: UserPublic) {
  saveRecent(query.value)
  router.push({ name: 'user-profile', params: { id: u.id } })
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
  return formatDateShort(d, locale.value)
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
.gs__results :deep(.gs__group) + :deep(.gs__group) { margin-top: 6px; }
.gs__results :deep(.gs__group-title) {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  padding: 10px 10px 6px;
}
.gs__results :deep(.gs__item) {
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
.gs__results :deep(.gs__item--active),
.gs__results :deep(.gs__item:hover) {
  background: var(--color-bg-muted);
}
.gs__results :deep(.gs__item--active) {
  background: var(--color-brand-ice);
}
.gs__results :deep(.gs__item-icon) { color: var(--color-brand-sky); flex-shrink: 0; }
.gs__results :deep(.gs__item-title) {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gs__results :deep(.gs__item-meta) {
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

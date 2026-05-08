<template>
  <section v-if="department" class="profile-card profile-card--wide colleagues-card">
    <header class="profile-card__head colleagues-head">
      <h2 class="profile-card__title">
        {{ t('users.profile.colleagues.title', { department }) }}
      </h2>
      <span v-if="!loading && total > 0" class="colleagues-count">
        {{ total }}
      </span>
    </header>

    <div v-if="loading" class="colleagues-loading">
      <n-spin size="small" />
    </div>

    <div v-else-if="visibleColleagues.length === 0" class="colleagues-empty">
      {{ t('users.profile.colleagues.empty') }}
    </div>

    <ul v-else class="colleagues-grid" role="list">
      <li v-for="c in visibleColleagues" :key="c.id" class="colleague-item">
        <router-link :to="{ name: 'user-profile', params: { id: c.id } }" class="colleague-link">
          <n-avatar round :size="40" :src="c.avatar_url ?? undefined" class="colleague-avatar">
            <template v-if="!c.avatar_url">{{ initials(c.full_name) }}</template>
          </n-avatar>
          <span class="colleague-text">
            <span class="colleague-name">{{ c.full_name }}</span>
            <span v-if="c.position" class="colleague-position">{{ c.position }}</span>
          </span>
        </router-link>
      </li>
    </ul>

    <div v-if="!loading && hasMore" class="colleagues-actions">
      <n-button quaternary size="small" @click="expanded = !expanded">
        {{ expanded
          ? t('users.profile.colleagues.collapse')
          : t('users.profile.colleagues.showAll', { count: total - INITIAL_LIMIT }) }}
      </n-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAvatar, NButton, NSpin } from 'naive-ui'
import { fetchUsers, type UserPublic } from '../../api/users'

const props = defineProps<{
  department: string | null | undefined
  excludeUserId?: string | null
}>()

const { t } = useI18n()

const INITIAL_LIMIT = 10
const FETCH_LIMIT = 200

const colleagues = ref<UserPublic[]>([])
const total = ref(0)
const loading = ref(false)
const expanded = ref(false)

const filtered = computed(() =>
  colleagues.value.filter((u) => u.id !== props.excludeUserId)
)

const visibleColleagues = computed(() =>
  expanded.value ? filtered.value : filtered.value.slice(0, INITIAL_LIMIT)
)

const hasMore = computed(() => filtered.value.length > INITIAL_LIMIT)

function initials(name: string): string {
  return name.split(' ').slice(0, 2).map((w) => w[0] ?? '').join('').toUpperCase()
}

async function load(department: string) {
  loading.value = true
  expanded.value = false
  try {
    const res = await fetchUsers({ department, page: 1, page_size: FETCH_LIMIT })
    const items = (res.items ?? []).filter((u) => u.id !== props.excludeUserId)
    colleagues.value = items
    total.value = items.length
  } catch {
    colleagues.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

watch(
  () => props.department,
  (dep) => {
    if (dep) {
      void load(dep)
    } else {
      colleagues.value = []
      total.value = 0
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.colleagues-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.colleagues-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;
}
.colleagues-count {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-muted);
  background: var(--color-bg-soft, rgba(0, 0, 0, 0.04));
  padding: 2px 10px;
  border-radius: var(--radius-pill);
}
.colleagues-loading,
.colleagues-empty {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 4px 0;
}
.colleagues-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.colleague-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-md, 8px);
  text-decoration: none;
  color: inherit;
  transition: background var(--t-fast, 0.15s);
  min-width: 0;
}
.colleague-link:hover {
  background: var(--color-bg-soft, rgba(0, 0, 0, 0.04));
}
.colleague-avatar {
  flex-shrink: 0;
}
.colleague-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.colleague-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.colleague-position {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.colleagues-actions {
  display: flex;
  justify-content: center;
  margin-top: 4px;
}
</style>

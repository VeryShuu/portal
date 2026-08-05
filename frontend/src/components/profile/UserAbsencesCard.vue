<template>
  <section
    v-if="hasAbsences"
    class="profile-card profile-card--wide absences-card"
  >
    <header class="profile-card__head">
      <h2 class="profile-card__title">
        {{ t('users.profile.absences.title') }}
      </h2>
      <span
        v-if="total > 0"
        class="absences-count"
      >
        {{ total }}
      </span>
    </header>

    <div
      v-if="loading"
      class="absences-loading"
    >
      <n-spin size="small" />
    </div>

    <ul
      v-else
      class="absences-list"
    >
      <li
        v-for="(a, idx) in items"
        :key="`${a.kind}-${a.start_date}-${idx}`"
        class="absence-item"
        :class="`absence-item--${a.kind}`"
      >
        <span class="absence-date">{{ periodLabel(a) }}</span>
        <span class="absence-reason">{{ kindLabel(a.kind) }}</span>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSpin } from 'naive-ui'
import { fetchUserAbsences, type UserAbsence } from '../../api/users'
import { formatDateShort } from '../../utils/formatDate'

const props = defineProps<{
  userId: string
  lang?: string | null
}>()

const { t, locale } = useI18n()

const items = ref<UserAbsence[]>([])
const total = ref(0)
const loading = ref(false)

const hasAbsences = computed(() => !loading.value && (items.value?.length ?? 0) > 0)

const effectiveLang = computed(() => props.lang ?? (locale.value === 'ru' ? 'ru' : 'en'))

// Человекочитаемые метки видов отсутствий. Согласовано с ABSENCE_KIND_VALUES
// в backend (models/erp_sync.py) и absences_parser._KIND_MAP.
function kindLabel(kind: string): string {
  return t(`users.profile.absences.kinds.${kind}`)
}

function periodLabel(a: UserAbsence): string {
  const start = formatDateShort(a.start_date, effectiveLang.value)
  // Однодневный отгул/болезнь — период без диапазона.
  if (a.start_date === a.end_date) return start
  const end = formatDateShort(a.end_date, effectiveLang.value)
  // Если старт и конец в одном месяце — не дублируем месяц в конце
  // («10 – 20 авг» вместо «10 авг – 20 авг»).
  if (start.endsWith(end.split(' ').slice(-1)[0])) {
    return `${start.split(' ')[0]} – ${end}`
  }
  return `${start} – ${end}`
}

async function load(userId: string) {
  loading.value = true
  try {
    const res = await fetchUserAbsences(userId)
    items.value = res.items
    total.value = res.total
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

watch(
  () => props.userId,
  (id) => {
    if (id) void load(id)
    else {
      items.value = []
      total.value = 0
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.absences-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.profile-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;
}
.absences-count {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-muted);
  background: var(--color-bg-soft, rgba(0, 0, 0, 0.04));
  padding: 2px 10px;
  border-radius: var(--radius-pill);
}
.absences-loading {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 4px 0;
}
.absences-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.absence-item {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 6px 10px;
  border-radius: var(--radius-md, 8px);
  background: var(--color-bg-soft, rgba(0, 0, 0, 0.03));
}
.absence-date {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  min-width: 120px;
}
.absence-reason {
  font-size: 13px;
  color: var(--color-text-muted);
}
@media (max-width: 540px) {
  .absence-item {
    flex-direction: column;
    gap: 2px;
  }
  .absence-date {
    min-width: 0;
  }
}
</style>

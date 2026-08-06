<script setup lang="ts">
/**
 * Универсальная аватарка пользователя с кольцом статуса присутствия.
 *
 * Заменяет дублированный инлайн-``<n-avatar>`` в 7+ местах портала. Источник
 * статуса — вычисляемая колонка ``current_status`` (миграция 093, ERP-only):
 * ``working`` / ``vacation`` / ``sick`` / ``business_trip``. Кольцо рисуется
 * только для отсутствующих (не ``working``); tooltip показывает локализованную
 * метку категории + дату окончания («Отпуск / отгул · до 15 авг»).
 *
 * Если у объекта нет ``current_status`` (например, helpdesk-сообщение без
 * user_id) — кольцо не рисуется, компонент ведёт себя как обычная аватарка.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAvatar } from 'naive-ui'
import { formatDateShort } from '@/utils/formatDate'

/** Минимальный «пользовательский» профиль — общий знаменатель UserMe/UserPublic/Birthday/NewsAuthor. */
interface AvatarUser {
  avatar_url?: string | null
  full_name?: string | null
  current_status?: import('@/api/users').UserStatusCategory | null
  current_status_until?: string | null
}

const props = withDefaults(
  defineProps<{
    user: AvatarUser
    size?: number
    /** Показывать ли кольцо для working (по умолчанию — нет, только для отсутствующих). */
    showWorkingRing?: boolean
  }>(),
  {
    size: 48,
    showWorkingRing: false,
  },
)

const { t, locale } = useI18n()

const initials = computed(() => {
  const name = props.user.full_name?.trim() ?? ''
  if (!name) return '?'
  const parts = name.split(/\s+/).filter(Boolean)
  const a = parts[0]?.[0] ?? ''
  const b = parts[1]?.[0] ?? ''
  return (a + b).toUpperCase() || '?'
})

/** Категория статуса, для которой рисуем кольцо (null = без кольца). */
const ringCategory = computed<import('@/api/users').UserStatusCategory | null>(() => {
  const status = props.user.current_status
  if (!status) return null
  if (status === 'working' && !props.showWorkingRing) return null
  return status
})

const ringClass = computed(() =>
  ringCategory.value ? `user-avatar--${ringCategory.value}` : '',
)

/** Локализованная подпись для tooltip (категория + «до {date}»). */
const tooltipText = computed(() => {
  const cat = ringCategory.value
  if (!cat) return ''
  const label = t(`users.presence.${cat}`)
  const until = props.user.current_status_until
  if (!until) return label
  return `${label} · ${t('users.presence.until', { date: formatDateShort(until, locale.value) })}`
})
</script>

<template>
  <span
    class="user-avatar"
    :class="ringClass"
    :title="tooltipText"
  >
    <n-avatar
      round
      :size="size"
      :src="user.avatar_url ?? undefined"
      class="user-avatar__img"
    >
      <template v-if="!user.avatar_url">
        {{ initials }}
      </template>
    </n-avatar>
  </span>
</template>

<style scoped>
/* Wrapper обжимает n-avatar без padding/фикс.размера — геометрия кольца
   точно повторяет круг аватара (фикс бага «овал»: раньше width/height=size
   + padding:3px при внутреннем n-avatar size → искажение пропорций).
   Ring рисуется через box-shadow на самом wrapper, который круглый
   (border-radius:50%) и того же размера, что аватар. Резерв под тень даём
   через margin, чтобы layout не прыгал при появлении кольца. */
.user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  /* Резерв 3px со всех сторон под box-shadow ring (не даёт layout сдвигаться,
     когда ring появляется/исчезает). */
  margin: 3px;
  line-height: 0;
}

.user-avatar__img {
  display: block;
}

/* Ring через box-shadow — рисуется по круглому wrapper, не искажая аватар.
   Цвет берётся из дизайн-токенов (tokens.css). */
.user-avatar--working {
  box-shadow: 0 0 0 2px var(--presence-ring-working);
}

.user-avatar--vacation {
  box-shadow: 0 0 0 3px var(--presence-ring-vacation);
}

.user-avatar--sick {
  box-shadow: 0 0 0 3px var(--presence-ring-sick);
}

.user-avatar--business_trip {
  box-shadow: 0 0 0 3px var(--presence-ring-business_trip);
}
</style>

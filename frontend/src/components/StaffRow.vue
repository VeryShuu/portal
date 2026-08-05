<template>
  <tr
    class="staff-row"
    :tabindex="0"
    role="link"
    @click="goToProfile"
    @keydown.enter="goToProfile"
  >
    <td class="staff-row__name">
      <div class="staff-row__name-inner">
        <span
          class="staff-row__name-text"
          v-html="hl(user.full_name)"
        />
        <span
          v-if="user.current_status && user.current_status !== 'working'"
          class="staff-row__presence"
          :class="`staff-row__presence--${user.current_status}`"
        >
          {{ presenceLabel }}
        </span>
      </div>
    </td>
    <td class="staff-row__position cell-position">
      <span v-html="hl(user.position)" />
    </td>
    <td class="staff-row__internal cell-internal">
      <template v-if="user.phone">
        <a
          class="mono mono--lg"
          :href="`tel:${user.phone}`"
          @click.stop
          v-html="hl(formatPhone(user.phone))"
        />
        <button
          class="copy-btn"
          type="button"
          :title="t('staff.copy')"
          @click.stop="copyValue(formatPhone(user.phone!), t('staff.fields.internalPhone'))"
        >
          <n-icon :size="14">
            <CopyOutline />
          </n-icon>
        </button>
      </template>
    </td>
    <td class="staff-row__phone cell-mobile">
      <template v-if="mobilePhone">
        <a
          :href="`tel:${mobilePhone}`"
          @click.stop
        >{{ mobilePhone }}</a>
        <button
          class="copy-btn"
          type="button"
          :title="t('staff.copy')"
          @click.stop="copyValue(mobilePhone, t('staff.fields.mobilePhone'))"
        >
          <n-icon :size="14">
            <CopyOutline />
          </n-icon>
        </button>
      </template>
    </td>
    <td class="staff-row__email">
      <template v-if="user.email">
        <a
          :href="`mailto:${user.email}`"
          @click.stop
          v-html="hl(user.email)"
        />
        <button
          class="copy-btn"
          type="button"
          :title="t('staff.copy')"
          @click.stop="copyValue(user.email, t('staff.fields.email'))"
        >
          <n-icon :size="14">
            <CopyOutline />
          </n-icon>
        </button>
      </template>
    </td>
    <td class="staff-row__office cell-office">
      {{ office }}
    </td>
  </tr>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NIcon, useMessage } from 'naive-ui'
import { CopyOutline } from '@vicons/ionicons5'
import type { UserPublic } from '../api/users'
import { usePhoneFormat } from '../composables/usePhoneFormat'
import { formatDateShort } from '../utils/formatDate'

const props = defineProps<{
  user: UserPublic
  hl: (text: string | null | undefined) => string
}>()

const router = useRouter()
const { t, locale } = useI18n()
const message = useMessage()
const { formatPhone } = usePhoneFormat()

// Текстовая пометка отсутствия в табличном режиме справочника (рядом с ФИО).
// Кольцо аватарки здесь не рисуется (в таблице аватарок нет) — только подпись.
const presenceLabel = computed(() => {
  const status = props.user.current_status
  if (!status || status === 'working') return ''
  const label = t(`users.presence.${status}`)
  const until = props.user.current_status_until
  if (!until) return label
  return `${label} · ${t('users.presence.until', { date: formatDateShort(until, locale.value) })}`
})

const mobilePhone = computed(() => {
  const v = props.user.attributes?.mobile
  return typeof v === 'string' ? v : ''
})

const office = computed(() => {
  const v = props.user.attributes?.city
  return typeof v === 'string' ? v : ''
})

function goToProfile() {
  if (typeof window !== 'undefined') {
    const sel = window.getSelection()
    if (sel && sel.toString().length > 0) return
  }
  router.push(`/users/${props.user.id}`)
}

async function copyValue(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value)
    message.success(t('staff.copied', { label }))
  } catch {
    message.error(t('staff.copyFailed'))
  }
}
</script>

<style scoped>
.staff-row {
  cursor: pointer;
  transition: background-color 0.15s ease;
}
.staff-row:hover {
  background-color: var(--n-merged-color-hover, rgba(0, 0, 0, 0.04));
}
.staff-row td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.06));
  vertical-align: middle;
  font-size: 14px;
}
/* Ячейка имени: ФИО + пометка отсутствия в одной строке (nowrap — пометка не
   переносится вниз и не ломает высоту строки). ФИО НЕ обрезается: таблица
   скроллится горизонтально при переполнении. Пометка зафиксирована справа. */
.staff-row__name-inner {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.staff-row__name-text {
  flex: 0 1 auto;
  font-weight: 500;
  color: var(--color-text);
}
.staff-row__presence {
  flex: none;
  margin-left: 8px;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 999px;
  vertical-align: middle;
  color: var(--color-text-muted);
  background: rgba(0, 0, 0, 0.05);
}
.staff-row__presence--vacation {
  color: var(--presence-ring-vacation);
  background: rgba(245, 158, 11, 0.12);
}
.staff-row__presence--sick {
  color: var(--presence-ring-sick);
  background: rgba(190, 18, 60, 0.1);
}
.staff-row__presence--business_trip {
  color: var(--presence-ring-business_trip);
  background: rgba(139, 92, 246, 0.12);
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
}
.mono--lg {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.staff-row__internal,
.staff-row__phone {
  font-variant-numeric: tabular-nums;
}
.copy-btn {
  margin-left: 6px;
  padding: 2px 4px;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s ease, background-color 0.15s ease;
  vertical-align: middle;
}
.staff-row:hover .copy-btn,
.copy-btn:focus-visible {
  opacity: 1;
}
.copy-btn:hover {
  background: var(--n-merged-color-hover, rgba(0, 0, 0, 0.06));
  color: var(--color-text);
}
.staff-row a {
  color: inherit;
  text-decoration: none;
}
.staff-row a:hover {
  text-decoration: underline;
}
@media (hover: none) {
  .copy-btn { opacity: 1; }
}
@media (max-width: 1024px) {
  .cell-office { display: none; }
}
@media (max-width: 768px) {
  .cell-internal { display: none; }
}
@media (max-width: 480px) {
  .cell-position { display: none; }
}
</style>

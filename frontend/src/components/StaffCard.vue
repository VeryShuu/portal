<template>
  <div
    class="staff-card"
    tabindex="0"
    role="link"
    @click="goToProfile"
    @keydown.enter="goToProfile"
  >
    <div class="staff-card__head">
      <n-avatar
        round
        :size="48"
        :src="user.avatar_url ?? undefined"
        class="staff-card__avatar"
      >
        {{ initials }}
      </n-avatar>
      <div class="staff-card__main">
        <div
          class="staff-card__name"
          v-html="hl(user.full_name)"
        />
        <div
          class="staff-card__position"
          :title="user.position ?? ''"
        >
          <span v-html="hl(user.position)" />
        </div>
      </div>
    </div>

    <n-tag
      v-if="user.department"
      size="small"
      class="staff-card__dept"
      :title="user.department"
    >
      <span class="staff-card__dept-text">{{ user.department }}</span>
    </n-tag>

    <ul class="staff-card__contacts">
      <li v-if="user.phone">
        <n-icon
          :size="14"
          class="ic"
        >
          <CallOutline />
        </n-icon>
        <a
          class="mono"
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
          <n-icon :size="13">
            <CopyOutline />
          </n-icon>
        </button>
      </li>
      <li v-if="mobilePhone">
        <n-icon
          :size="14"
          class="ic"
        >
          <PhonePortraitOutline />
        </n-icon>
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
          <n-icon :size="13">
            <CopyOutline />
          </n-icon>
        </button>
      </li>
      <li v-if="user.email">
        <n-icon
          :size="14"
          class="ic"
        >
          <MailOutline />
        </n-icon>
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
          <n-icon :size="13">
            <CopyOutline />
          </n-icon>
        </button>
      </li>
      <li v-if="office">
        <n-icon
          :size="14"
          class="ic"
        >
          <LocationOutline />
        </n-icon>
        <span>{{ office }}</span>
      </li>
    </ul>

    <ul
      v-if="extraAttributes.length"
      class="staff-card__extras"
    >
      <li
        v-for="attr in extraAttributes"
        :key="attr.key"
      >
        <span class="staff-card__extra-label">{{ attr.label }}:</span>
        <span class="staff-card__extra-value">{{ attr.value }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NAvatar, NIcon, NTag, useMessage } from 'naive-ui'
import {
  CallOutline,
  CopyOutline,
  LocationOutline,
  MailOutline,
  PhonePortraitOutline,
} from '@vicons/ionicons5'
import type { UserPublic } from '../api/users'
import type { UserAttributeMappingSchema } from '../api/userAttributeMappings'
import { usePhoneFormat } from '../composables/usePhoneFormat'

const RESERVED_ATTRS = new Set(['internal_phone', 'city', 'mobile'])

const props = defineProps<{
  user: UserPublic
  hl: (text: string | null | undefined) => string
  attributeSchema?: UserAttributeMappingSchema[]
  lang?: 'ru' | 'en'
}>()

const router = useRouter()
const { t } = useI18n()
const message = useMessage()
const { formatPhone } = usePhoneFormat()

const initials = computed(() => {
  const name = props.user.full_name?.trim() ?? ''
  if (!name) return '?'
  const parts = name.split(/\s+/).filter(Boolean)
  const a = parts[0]?.[0] ?? ''
  const b = parts[1]?.[0] ?? ''
  return (a + b).toUpperCase() || '?'
})

const mobilePhone = computed(() => {
  const v = props.user.attributes?.mobile
  return typeof v === 'string' ? v : ''
})

const office = computed(() => {
  const v = props.user.attributes?.city
  return typeof v === 'string' ? v : ''
})

const extraAttributes = computed(() => {
  const schema = props.attributeSchema ?? []
  const attrs = props.user.attributes ?? {}
  const lang = props.lang ?? 'ru'
  return schema
    .filter((s) => !RESERVED_ATTRS.has(s.attr_key))
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((s) => {
      const raw = attrs[s.attr_key]
      const value = Array.isArray(raw) ? raw.join(', ') : (raw ?? '')
      return {
        key: s.attr_key,
        label: lang === 'en' && s.label_en ? s.label_en : s.label_ru,
        value: typeof value === 'string' ? value : String(value),
      }
    })
    .filter((x) => x.value)
})

function goToProfile() {
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
.staff-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 10px;
  background: var(--color-surface, #fff);
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  cursor: pointer;
  transition: box-shadow 0.15s ease, transform 0.15s ease, border-color 0.15s ease;
}
.staff-card:hover,
.staff-card:focus-visible {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  border-color: var(--color-brand-navy, #1f3a5f);
  outline: none;
}
.staff-card__head {
  display: flex;
  gap: 12px;
  align-items: center;
}
.staff-card__avatar {
  flex: 0 0 auto;
  background: var(--color-brand-navy, #1f3a5f);
  color: #fff;
  font-weight: 600;
}
.staff-card__main {
  min-width: 0;
  flex: 1;
}
.staff-card__name {
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text);
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.staff-card__position {
  font-size: 13px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}
.staff-card__dept {
  align-self: flex-start;
  max-width: 100%;
  overflow: hidden;
}
.staff-card__dept :deep(.n-tag__content) {
  max-width: 100%;
  overflow: hidden;
}
.staff-card__dept-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
.staff-card__contacts {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}
.staff-card__contacts li {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text);
  min-width: 0;
}
.staff-card__contacts a {
  color: inherit;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.staff-card__contacts a:hover {
  text-decoration: underline;
}
.ic {
  color: var(--color-text-muted);
  flex: 0 0 auto;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.copy-btn {
  margin-left: auto;
  padding: 2px 4px;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s ease, background-color 0.15s ease;
}
.staff-card:hover .copy-btn,
.copy-btn:focus-visible {
  opacity: 1;
}
.copy-btn:hover {
  background: var(--n-merged-color-hover, rgba(0, 0, 0, 0.06));
  color: var(--color-text);
}
@media (hover: none) {
  .copy-btn { opacity: 1; }
}
.staff-card__extras {
  list-style: none;
  margin: 0;
  padding: 8px 0 0 0;
  border-top: 1px dashed var(--n-border-color, rgba(0, 0, 0, 0.08));
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12.5px;
  color: var(--color-text-muted);
}
.staff-card__extra-label {
  font-weight: 500;
  margin-right: 4px;
}
</style>

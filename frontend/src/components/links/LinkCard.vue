<template>
  <div
    class="link-card-wrap"
    :class="{ 'link-card-wrap--draggable': canDrag }"
    :data-id="item.id"
  >
    <component
      :is="linkComponent"
      v-bind="linkProps"
      class="link-card"
      :draggable="false"
    >
      <span
        v-if="canDrag"
        class="drag-handle"
        :title="t('common.dragToReorder')"
        :aria-label="t('common.dragToReorder')"
        @click.prevent.stop
      >
        <n-icon size="16"><ReorderTwoOutline /></n-icon>
      </span>
      <div class="link-icon">
        <img
          v-if="item.iconUrl"
          :src="item.iconUrl"
          :alt="item.title"
          @error="onIconError($event)"
        >
        <img
          v-else-if="faviconFor(item.url)"
          :src="faviconFor(item.url)!"
          :alt="item.title"
          @error="onIconError($event)"
        >
        <n-icon
          v-else
          size="22"
        ><LinkOutline /></n-icon>
      </div>
      <div class="link-info">
        <div class="link-title">
          <span class="link-title-text">{{ item.title }}</span>
          <span
            v-if="item.supportsSso"
            class="sso-badge"
            :title="t('links.sso')"
          >
            <n-icon size="12"><ShieldCheckmarkOutline /></n-icon>
            SSO
          </span>
        </div>
        <div
          v-if="item.description"
          class="link-desc"
        >{{ item.description }}</div>
        <div class="link-url">{{ shortUrl(item.url) }}</div>
      </div>
      <n-icon
        class="link-arrow"
        size="16"
      ><component :is="isInternal ? ArrowForwardOutline : OpenOutline" /></n-icon>
    </component>
    <div
      v-if="hasActions"
      class="link-admin-actions"
    >
      <n-button
        v-if="item.kind === 'link' && isAdmin"
        size="tiny"
        quaternary
        circle
        :title="t('common.edit')"
        :aria-label="t('common.edit')"
        @click.prevent.stop="emit('edit', item)"
      >
        <template #icon>
          <n-icon size="13">
            <CreateOutline />
          </n-icon>
        </template>
      </n-button>
      <n-button
        size="tiny"
        quaternary
        circle
        type="error"
        :title="item.kind === 'bookmark' ? t('bookmarks.remove') : t('common.delete')"
        :aria-label="item.kind === 'bookmark' ? t('bookmarks.remove') : t('common.delete')"
        @click.prevent.stop="emit('delete', item)"
      >
        <template #icon>
          <n-icon size="13">
            <TrashOutline />
          </n-icon>
        </template>
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { NIcon, NButton } from 'naive-ui'
import {
  LinkOutline, ShieldCheckmarkOutline, OpenOutline, ArrowForwardOutline,
  CreateOutline, TrashOutline, ReorderTwoOutline,
} from '@vicons/ionicons5'
import { useFavicon } from '../../composables/useFavicon'
import { isInternalLinkUrl } from '../../utils/url'
import { BASE_URL } from '../../api'
import type { NormalizedItem } from '../../api/links'

const props = defineProps<{
  item: NormalizedItem
  canDrag: boolean
  isAdmin: boolean
}>()

const emit = defineEmits<{
  edit: [item: NormalizedItem]
  delete: [item: NormalizedItem]
}>()

const { t } = useI18n()
const { faviconFor, shortUrl, onIconError } = useFavicon()

const hasActions = computed(() =>
  props.item.kind === 'bookmark' || props.isAdmin,
)

const isInternal = computed(() =>
  props.item.kind === 'link'
  && !props.item.supportsSso
  && isInternalLinkUrl(props.item.url),
)

const href = computed(() => {
  if (props.item.kind === 'link' && props.item.supportsSso) {
    return `${BASE_URL}/links/${props.item.id}/sso-redirect`
  }
  return props.item.url
})

const linkComponent = computed(() => (isInternal.value ? RouterLink : 'a'))

const linkProps = computed(() =>
  isInternal.value
    ? { to: props.item.url }
    : { href: href.value, target: '_blank', rel: 'noopener noreferrer' },
)
</script>

<style scoped>
.link-card-wrap {
  position: relative;
  height: 100%;
}
.link-card-wrap:hover .link-admin-actions {
  opacity: 1;
}
.link-admin-actions {
  position: absolute;
  top: 50%;
  right: 10px;
  transform: translateY(-50%);
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
  background: var(--color-surface);
  border-radius: var(--radius-md);
  padding: 4px;
  box-shadow: var(--shadow-sm);
  z-index: 2;
}

.link-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  cursor: pointer;
  position: relative;
  text-align: left;
  font-family: inherit;
  width: 100%;
  height: 100%;
  text-decoration: none;
  color: inherit;
  transition: transform var(--t-base), box-shadow var(--t-base), border-color var(--t-base);
}
.link-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--color-brand-sky);
}
.link-card:hover .link-arrow {
  color: var(--color-brand-red);
  transform: translate(2px, -2px);
}

.link-icon {
  flex-shrink: 0;
  width: 46px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: #fff;
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
  color: var(--color-brand-navy);
  transition: box-shadow var(--t-base);
}
[data-theme='dark'] .link-icon {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.7);
}
.link-card:hover .link-icon {
  box-shadow: var(--shadow-md);
}
.link-icon img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.link-info {
  flex: 1;
  min-width: 0;
}
.link-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.link-title-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.link-desc {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-url {
  font-size: 11px;
  color: var(--color-text-subtle);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-arrow {
  flex-shrink: 0;
  color: var(--color-text-subtle);
  transition: transform var(--t-base), color var(--t-base);
}

.sso-badge {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  gap: 3px;
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: rgba(74, 144, 196, 0.12);
  color: var(--color-brand-sky);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.link-card-wrap--draggable .drag-handle { cursor: grab; }
.link-card-wrap--draggable .drag-handle:active { cursor: grabbing; }

.sortable-ghost > .link-card {
  opacity: 0.35;
  border-color: var(--color-brand-sky);
  border-style: dashed;
  background: transparent;
}
.sortable-ghost > .link-card > * { visibility: hidden; }

.sortable-drag > .link-card {
  box-shadow: var(--shadow-md);
  transform: rotate(0.6deg);
  cursor: grabbing;
}

.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  flex-shrink: 0;
  margin-right: -4px;
  margin-left: -4px;
  color: var(--color-text-subtle);
  opacity: 0;
  transition: opacity var(--t-base);
  cursor: grab;
}
.link-card-wrap--draggable:hover .drag-handle,
.link-card-wrap--draggable:focus-within .drag-handle {
  opacity: 0.7;
}
.drag-handle:hover { opacity: 1 !important; }

@media (max-width: 640px) {
  .link-card-wrap--draggable .drag-handle { opacity: 0.7; }
}
</style>

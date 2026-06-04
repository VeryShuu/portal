<template>
  <div class="my-shares-page u-page-wrap">
    <h1 class="my-shares-page__title">
      {{ t('photos.myShares.title') }}
    </h1>

    <div
      v-if="loading"
      class="my-shares-page__loading"
    >
      {{ t('common.loading') }}
    </div>
    <template v-else>
      <section
        v-if="photoShares.length"
        class="shares-section"
      >
        <h2 class="shares-section__title">
          {{ t('photos.myShares.photoLinks') }}
        </h2>
        <ul class="shares-list">
          <li
            v-for="token in photoShares"
            :key="token.id"
            class="share-row"
          >
            <img
              :src="thumbUrl(token.photo_id, 200)"
              class="share-row__thumb"
              :alt="token.photo_id"
            >
            <div class="share-row__info">
              <a
                :href="absoluteUrl(token.url)"
                target="_blank"
                rel="noopener noreferrer"
                class="share-row__url"
              >{{ absoluteUrl(token.url) }}</a>
              <span class="share-row__expiry">
                {{ token.expires_at
                  ? t('photos.myShares.expires') + ' ' + new Date(token.expires_at).toLocaleDateString()
                  : t('photos.myShares.noExpiry') }}
              </span>
            </div>
            <div class="share-row__actions">
              <n-button
                size="tiny"
                @click="copyUrl(token.url)"
              >
                {{ t('photos.myShares.copyUrl') }}
              </n-button>
              <n-button
                size="tiny"
                type="error"
                ghost
                @click="doRevokePhoto(token)"
              >
                {{ t('photos.myShares.revoke') }}
              </n-button>
            </div>
          </li>
        </ul>
      </section>

      <section
        v-if="folderShares.length"
        class="shares-section"
      >
        <h2 class="shares-section__title">
          {{ t('photos.myShares.folderLinks') }}
        </h2>
        <ul class="shares-list">
          <li
            v-for="token in folderShares"
            :key="token.id"
            class="share-row"
          >
            <div class="share-row__icon">
              📁
            </div>
            <div class="share-row__info">
              <strong
                v-if="token.folder_name"
                class="share-row__folder-name"
              >{{ token.folder_name }}</strong>
              <a
                :href="absoluteUrl(token.url)"
                target="_blank"
                rel="noopener noreferrer"
                class="share-row__url"
              >{{ absoluteUrl(token.url) }}</a>
              <span class="share-row__expiry">
                {{ token.expires_at
                  ? t('photos.myShares.expires') + ' ' + new Date(token.expires_at).toLocaleDateString()
                  : t('photos.myShares.noExpiry') }}
              </span>
            </div>
            <div class="share-row__actions">
              <n-button
                size="tiny"
                @click="copyUrl(token.url)"
              >
                {{ t('photos.myShares.copyUrl') }}
              </n-button>
              <n-button
                size="tiny"
                type="error"
                ghost
                @click="doRevokeFolder(token)"
              >
                {{ t('photos.myShares.revoke') }}
              </n-button>
            </div>
          </li>
        </ul>
      </section>

      <EmptyState
        v-if="!photoShares.length && !folderShares.length"
        variant="photo"
        :title="t('photos.myShares.empty')"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, useMessage } from 'naive-ui'
import EmptyState from '@/components/EmptyState.vue'
import {
  thumbUrl,
  type PhotoShareToken, type FolderShareToken,
} from '@/api/photos'
import { useMySharesQuery, useRevokePhotoShareMutation, useRevokeFolderShareMutation } from '@/queries/photos'

const { t } = useI18n()
const message = useMessage()

const { data: sharesData, isLoading: loading } = useMySharesQuery()
const photoShares = computed(() => sharesData.value?.photo_tokens ?? [])
const folderShares = computed(() => sharesData.value?.folder_tokens ?? [])

const revokePhotoMutation = useRevokePhotoShareMutation()
const revokeFolderMutation = useRevokeFolderShareMutation()

function absoluteUrl(url: string) {
  if (!url) return ''
  return url.startsWith('http') ? url : new URL(url, window.location.origin).href
}

async function copyUrl(url: string) {
  try {
    await navigator.clipboard.writeText(absoluteUrl(url))
    message.success(t('common.copied'))
  } catch {
    message.error(t('common.copyFailed'))
  }
}

async function doRevokePhoto(token: PhotoShareToken) {
  try {
    await revokePhotoMutation.mutateAsync(token.id)
    message.success(t('photos.myShares.revoked'))
  } catch {
    message.error(t('errors.generic'))
  }
}

async function doRevokeFolder(token: FolderShareToken) {
  try {
    await revokeFolderMutation.mutateAsync(token.id)
    message.success(t('photos.myShares.revoked'))
  } catch {
    message.error(t('errors.generic'))
  }
}
</script>

<style scoped>
.my-shares-page__title { margin: 0 0 24px; font-size: 24px; }
.my-shares-page__loading { color: var(--color-text-muted); padding: 40px 0; text-align: center; }
.shares-section { margin-bottom: 32px; }
.shares-section__title { font-size: 16px; font-weight: 600; margin: 0 0 12px; }
.shares-list { list-style: none; margin: 0; padding: 0; }
.share-row {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 0; border-bottom: 1px solid var(--color-border);
}
.share-row:last-child { border-bottom: 0; }
.share-row__thumb {
  width: 48px; height: 48px; object-fit: cover;
  border-radius: var(--radius-sm); flex-shrink: 0;
}
.share-row__icon { font-size: 32px; flex-shrink: 0; width: 48px; text-align: center; }
.share-row__info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.share-row__folder-name { font-size: 13px; }
.share-row__url {
  font-size: 12px; color: var(--color-primary, #3b82f6);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.share-row__expiry { font-size: 11px; color: var(--color-text-muted); }
.share-row__actions { display: flex; gap: 6px; flex-shrink: 0; }
</style>

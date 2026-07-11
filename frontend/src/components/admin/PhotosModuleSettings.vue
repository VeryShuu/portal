<template>
  <div class="photos-module-settings">
    <div
      v-if="!modulesData?.photos?.enabled"
      class="module-disabled-hint"
    >
      {{ t('admin.modules.photos.disabledHint') }}
    </div>

    <template v-else>
      <section class="settings-section">
        <h4 class="settings-section__title">
          {{ t('admin.modules.photos.title') }}
        </h4>
        <div class="branding-fields">
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.modules.widgetLimit')"
              style="margin-bottom:0;max-width:220px"
            >
              <n-input-number
                v-model:value="photosForm.widget_limit"
                :min="1"
                :max="50"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.modules.photos.maxSizeMb')"
              style="margin-bottom:0;max-width:220px"
            >
              <n-input-number
                v-model:value="photosForm.max_size_mb"
                :min="1"
                :max="500"
              />
            </n-form-item>
          </div>
          <n-form-item
            :label="t('admin.modules.photos.allowedMime')"
            style="margin-bottom:0"
          >
            <n-input
              v-model:value="photosForm.allowed_mime"
              :placeholder="t('admin.modules.photos.allowedMimePlaceholder')"
            />
          </n-form-item>
          <n-form-item style="margin-bottom:0">
            <n-checkbox v-model:checked="photosForm.strip_gps">
              {{ t('admin.modules.photos.stripGps') }}
            </n-checkbox>
          </n-form-item>
        </div>
        <div class="settings-actions">
          <n-button
            type="primary"
            :loading="photosSaving"
            @click="onSavePhotos"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </section>

      <section class="settings-section">
        <h4 class="settings-section__title">
          {{ t('admin.modules.photoGallery.title') }}
        </h4>
        <div class="settings-section__hint">
          {{ t('admin.modules.photoGallery.hint') }}
        </div>
        <div
          class="branding-fields"
          style="margin-top:12px"
        >
          <n-form-item
            :label="t('admin.modules.photoGallery.modeLabel')"
            style="margin-bottom:0"
          >
            <n-radio-group v-model:value="galleryForm.mode">
              <n-radio value="internal">
                {{ t('admin.modules.photoGallery.modeInternal') }}
              </n-radio>
              <n-radio value="external">
                {{ t('admin.modules.photoGallery.modeExternal') }}
              </n-radio>
            </n-radio-group>
          </n-form-item>
          <template v-if="galleryForm.mode === 'external'">
            <n-form-item
              :label="t('admin.system.photoGalleryUrl')"
              style="margin-bottom:0"
            >
              <n-input
                v-model:value="galleryForm.url"
                :placeholder="t('admin.system.photoGalleryUrlPlaceholder')"
                clearable
              />
            </n-form-item>
            <div class="settings-section__hint">
              {{ t('admin.system.photoGalleryUrlHint') }}
            </div>
            <n-form-item style="margin-bottom:0">
              <n-checkbox v-model:checked="galleryForm.newTab">
                {{ t('admin.modules.photoGallery.newTab') }}
              </n-checkbox>
            </n-form-item>
          </template>
        </div>
        <div class="settings-actions">
          <n-button
            type="primary"
            :loading="gallerySaving"
            @click="onSaveGallery"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NCheckbox, NFormItem, NInput, NInputNumber, NRadio, NRadioGroup,
  useMessage,
} from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '../../api'
import { useModulesAdminQuery, useSystemSettingsQuery } from '../../queries/admin'
import { queryKeys } from '../../queries/keys'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()

const { data: modulesData } = useModulesAdminQuery()
const { data: sysSettingsData } = useSystemSettingsQuery()

const photosForm = reactive({
  widget_limit: 8,
  max_size_mb: 50,
  allowed_mime: 'image/jpeg,image/png,image/webp,image/heic,image/heif,image/gif',
  strip_gps: true,
})
const galleryForm = reactive({
  mode: 'external' as 'internal' | 'external',
  url: '',
  newTab: false,
})

const photosSaving = ref(false)
const gallerySaving = ref(false)

watch(modulesData, (data) => {
  if (!data?.photos) return
  photosForm.widget_limit = data.photos.widget_limit
  photosForm.max_size_mb = data.photos.max_size_mb
  photosForm.allowed_mime = (data.photos.allowed_mime || []).join(',')
  photosForm.strip_gps = data.photos.strip_gps
}, { immediate: true })

watch(sysSettingsData, (data) => {
  if (!data) return
  galleryForm.mode = ((data.photo_gallery_mode as string) || 'external') as 'internal' | 'external'
  galleryForm.url = (data.photo_gallery_url as string) || ''
  galleryForm.newTab = Boolean(data.photo_gallery_new_tab)
}, { immediate: true })

async function onSavePhotos() {
  photosSaving.value = true
  try {
    await api('/admin/modules/photos', {
      method: 'PUT',
      body: {
        enabled: modulesData.value?.photos?.enabled ?? true,
        widget_limit: photosForm.widget_limit,
        max_size_mb: photosForm.max_size_mb,
        allowed_mime: photosForm.allowed_mime.split(',').map((s) => s.trim()).filter(Boolean),
        strip_gps: photosForm.strip_gps,
      },
    })
    qc.invalidateQueries({ queryKey: queryKeys.admin.modules() })
    message.success(t('admin.modules.saved'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    photosSaving.value = false
  }
}

async function onSaveGallery() {
  gallerySaving.value = true
  try {
    await api('/admin/system/settings', {
      method: 'PATCH',
      body: {
        photo_gallery_url: galleryForm.url,
        photo_gallery_mode: galleryForm.mode,
        photo_gallery_new_tab: galleryForm.newTab,
      },
    })
    qc.invalidateQueries({ queryKey: queryKeys.admin.systemSettings() })
    message.success(t('admin.modules.saved'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    gallerySaving.value = false
  }
}
</script>

<style scoped>
.photos-module-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.module-disabled-hint {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 12px;
  border: 1px dashed var(--n-border-color, #ddd);
  border-radius: 8px;
}
.settings-section {
  border: 1px solid var(--n-border-color, #eaeaea);
  border-radius: 10px;
  padding: 16px;
  background: var(--color-surface, transparent);
}
.settings-section__title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
}
.settings-section__hint {
  font-size: 12px;
  color: var(--color-text-muted, #999);
  margin-bottom: 4px;
}
.branding-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.email-row-2 {
  display: flex;
  gap: 12px;
}
.settings-actions {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>

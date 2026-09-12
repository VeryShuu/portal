<template>
  <div>
    <div class="tab-toolbar">
      <n-input
        v-model:value="linkSearch"
        :placeholder="t('common.search')"
        clearable
        style="max-width:260px"
      >
        <template #prefix>
          <n-icon><SearchOutline /></n-icon>
        </template>
      </n-input>
      <n-button
        type="primary"
        @click="openAddLink"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('admin.links.add') }}
      </n-button>
    </div>

    <n-data-table
      :columns="linkColumns"
      :data="filteredLinks"
      :loading="loadingLinks"
      :pagination="{ pageSize: 20 }"
      :row-key="(row: ServiceLink) => row.id"
      striped
      class="data-table"
    />

    <n-modal
      v-model:show="linkModalOpen"
      :title="editingLink ? t('admin.links.editTitle') : t('admin.links.addTitle')"
      preset="card"
      style="width:540px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form
        ref="linkFormRef"
        :model="linkForm"
        :rules="linkRules"
        label-placement="top"
      >
        <div class="form-row">
          <n-form-item
            :label="t('admin.links.form.titleLabel')"
            path="title"
          >
            <n-input
              v-model:value="linkForm.title"
              :placeholder="t('admin.links.form.titlePlaceholder')"
            />
          </n-form-item>
          <n-form-item
            :label="t('admin.links.form.urlLabel')"
            path="url"
          >
            <n-input
              v-model:value="linkForm.url"
              :placeholder="t('admin.links.form.urlPlaceholder')"
            />
          </n-form-item>
        </div>
        <div class="url-hint">
          {{ t('admin.links.form.urlHint') }}
        </div>
        <div class="form-row">
          <n-form-item :label="t('admin.links.form.categoryLabel')">
            <n-input
              v-model:value="linkForm.category"
              :placeholder="t('admin.links.form.categoryPlaceholder')"
              clearable
            />
          </n-form-item>
          <n-form-item :label="t('admin.links.form.sortOrderLabel')">
            <n-input-number
              v-model:value="linkForm.sort_order"
              :min="0"
              style="width:100%"
            />
          </n-form-item>
        </div>
        <n-form-item :label="t('admin.links.form.descriptionLabel')">
          <n-input
            v-model:value="linkForm.description"
            type="textarea"
            :rows="2"
            :placeholder="t('admin.links.form.descriptionPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.links.form.kbUrlLabel')"
          path="kb_url"
        >
          <n-input
            v-model:value="linkForm.kb_url"
            :placeholder="t('admin.links.form.kbUrlPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item :label="t('admin.links.form.iconLabel')">
          <div class="icon-upload-row">
            <div
              v-if="iconPreview || (editingLink && editingLink.icon_url)"
              class="icon-preview-wrap"
            >
              <img
                :src="iconPreview || editingLink!.icon_url!"
                class="icon-preview"
                alt=""
              >
              <n-button
                size="tiny"
                circle
                quaternary
                type="error"
                class="icon-preview-remove"
                @click="removeIcon"
              >
                ×
              </n-button>
            </div>
            <n-upload
              accept="image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon"
              :max="1"
              :show-file-list="false"
              @change="onIconFileChange"
            >
              <n-button size="small">
                {{ t('admin.links.form.iconUploadBtn') }}
              </n-button>
            </n-upload>
          </div>
        </n-form-item>
        <div class="form-checks">
          <n-checkbox v-model:checked="linkForm.supports_sso">
            {{ t('admin.links.form.supportsSSO') }}
          </n-checkbox>
          <n-checkbox v-model:checked="linkForm.is_active">
            {{ t('admin.links.form.isActive') }}
          </n-checkbox>
          <n-checkbox v-model:checked="linkForm.show_on_home">
            {{ t('admin.links.form.showOnHome') }}
          </n-checkbox>
        </div>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="linkModalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="savingLink"
            @click="submitLink"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NDataTable, NButton, NInput, NInputNumber, NIcon, NModal, NForm, NFormItem,
  NCheckbox, NUpload,
} from 'naive-ui'
import { SearchOutline, AddOutline } from '@vicons/ionicons5'
import { type ServiceLink } from '../../../api/links'
import { useAdminLinksQuery } from '../../../queries/admin'
import { useLinkIconUpload } from '../../../composables/useLinkIconUpload'
import { useLinkForm } from '../../../composables/useLinkForm'
import { useLinkColumns } from '../../../composables/useLinkColumns'

const { t } = useI18n()
const linkSearch = ref('')

// Server state (TanStack Query).
const { data: linksData, isLoading: loadingLinks } = useAdminLinksQuery()
const links = computed(() => linksData.value?.items ?? [])
const filteredLinks = computed(() => {
  const q = linkSearch.value.trim().toLowerCase()
  if (!q) return links.value
  return links.value.filter(l =>
    l.title.toLowerCase().includes(q) ||
    l.url.toLowerCase().includes(q) ||
    (l.category ?? '').toLowerCase().includes(q),
  )
})

// Icon-upload: общий composable с LinkFormModal.
const { iconFile, iconPreview, iconRemoved, onIconFileChange, removeIcon, resetIconState } = useLinkIconUpload()

// Форма (state + CRUD) и колонки — вынесены в composables, страница = wiring.
const {
  linkModalOpen, savingLink, editingLink, linkFormRef, linkForm, linkRules,
  openAddLink, openEditLink, openDeleteLink, submitLink,
} = useLinkForm({ iconFile, iconRemoved, resetIconState })

const { linkColumns } = useLinkColumns(openEditLink, openDeleteLink)
</script>

<style scoped>
@import '../admin-tabs.css';

.url-hint {
  margin-top: -8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>

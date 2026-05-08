<template>
  <n-modal
    :show="show"
    :title="editingLink ? t('admin.links.editTitle') : t('admin.links.addTitle')"
    preset="card"
    style="width:540px;max-width:94vw"
    :mask-closable="false"
    @update:show="emit('update:show', $event)"
  >
    <n-form :model="linkForm" :rules="linkRules" ref="linkFormRef" label-placement="top">
      <div class="modal-form-row">
        <n-form-item :label="t('admin.links.form.titleLabel')" path="title">
          <n-input v-model:value="linkForm.title" :placeholder="t('admin.links.form.titlePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('admin.links.form.urlLabel')" path="url">
          <n-input v-model:value="linkForm.url" :placeholder="t('admin.links.form.urlPlaceholder')" />
        </n-form-item>
      </div>
      <div class="modal-form-row">
        <n-form-item :label="t('admin.links.form.categoryLabel')">
          <n-input v-model:value="linkForm.category" :placeholder="t('admin.links.form.categoryPlaceholder')" clearable />
        </n-form-item>
        <n-form-item :label="t('admin.links.form.sortOrderLabel')">
          <n-input-number v-model:value="linkForm.sort_order" :min="0" style="width:100%" />
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
      <n-form-item :label="t('admin.links.form.iconLabel')">
        <div class="icon-upload-row">
          <div v-if="iconPreview || (editingLink && editingLink.icon_url)" class="icon-preview-wrap">
            <img :src="iconPreview || editingLink!.icon_url!" class="icon-preview" alt="" />
            <n-button size="tiny" circle quaternary type="error" class="icon-preview-remove" @click="removeIcon">×</n-button>
          </div>
          <n-upload
            accept="image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon"
            :max="1"
            :show-file-list="false"
            @change="onIconFileChange"
          >
            <n-button size="small">{{ t('admin.links.form.iconUploadBtn') }}</n-button>
          </n-upload>
        </div>
      </n-form-item>
      <div class="modal-form-checks">
        <n-checkbox v-model:checked="linkForm.supports_sso">{{ t('admin.links.form.supportsSSO') }}</n-checkbox>
        <n-checkbox v-model:checked="linkForm.is_active">{{ t('admin.links.form.isActive') }}</n-checkbox>
      </div>
    </n-form>
    <template #footer>
      <div class="modal-footer">
        <n-button @click="emit('update:show', false)">{{ t('common.cancel') }}</n-button>
        <n-button type="primary" :loading="saving" @click="submit">{{ t('common.save') }}</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NModal, NForm, NFormItem, NInput, NInputNumber,
  NCheckbox, NUpload, NButton, useMessage,
} from 'naive-ui'
import { useLinkIconUpload } from '../../composables/useLinkIconUpload'
import { useLinksStore } from '../../stores/links'
import {
  createLink, updateLink, uploadLinkIcon, deleteLinkIcon,
  type ServiceLink, type CreateLinkDto,
} from '../../api/links'
import { isSafeHttpUrl } from '../../utils/url'

const props = defineProps<{
  show: boolean
  editingLink: ServiceLink | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  saved: []
}>()

const { t } = useI18n()
const store = useLinksStore()
const message = useMessage()
const { iconFile, iconPreview, iconRemoved, onIconFileChange, removeIcon, resetIconState } = useLinkIconUpload()

const saving = ref(false)
const linkFormRef = ref()

const emptyForm = () => ({
  title: '',
  url: '',
  description: null as string | null,
  category: null as string | null,
  sort_order: 0,
  supports_sso: false,
  is_active: true,
})
const linkForm = ref(emptyForm())

const linkRules = computed(() => ({
  title: [{ required: true, message: t('admin.links.form.required'), trigger: 'blur' }],
  url: [
    { required: true, message: t('admin.links.form.required'), trigger: 'blur' },
    {
      validator: (_: unknown, value: string) => isSafeHttpUrl(value),
      message: t('admin.links.form.invalidUrl'),
      trigger: 'blur',
    },
  ],
}))

watch(() => props.show, (val) => {
  if (!val) return
  if (props.editingLink) {
    linkForm.value = {
      title: props.editingLink.title,
      url: props.editingLink.url,
      description: props.editingLink.description,
      category: props.editingLink.category,
      sort_order: props.editingLink.sort_order,
      supports_sso: props.editingLink.supports_sso,
      is_active: props.editingLink.is_active,
    }
  } else {
    linkForm.value = emptyForm()
  }
  resetIconState()
})

async function submit() {
  try { await linkFormRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const dto: CreateLinkDto = {
      title: linkForm.value.title,
      url: linkForm.value.url,
      description: linkForm.value.description || null,
      category: linkForm.value.category || null,
      sort_order: linkForm.value.sort_order ?? 0,
      supports_sso: linkForm.value.supports_sso,
      is_active: linkForm.value.is_active,
    }

    let saved: ServiceLink
    if (props.editingLink) {
      saved = await updateLink(props.editingLink.id, dto)
      store.updateLinkItem(saved)
    } else {
      saved = await createLink(dto)
      store.addLink(saved)
    }

    if (iconFile.value) {
      const withIcon = await uploadLinkIcon(saved.id, iconFile.value)
      store.updateLinkItem(withIcon)
    } else if (iconRemoved.value && props.editingLink?.icon_url) {
      await deleteLinkIcon(saved.id)
      store.clearLinkIcon(saved.id)
    }

    message.success(t('admin.links.saved'))
    emit('update:show', false)
    emit('saved')
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}
.modal-form-checks {
  display: flex;
  gap: 24px;
  margin-top: 4px;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.icon-upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.icon-preview-wrap {
  position: relative;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
}
.icon-preview {
  width: 40px;
  height: 40px;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}
.icon-preview-remove {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 18px !important;
  height: 18px !important;
  min-width: 18px !important;
  font-size: 12px;
}
</style>

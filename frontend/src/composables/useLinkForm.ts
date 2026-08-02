import { ref, computed } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, type FormInst } from 'naive-ui'
import { type ServiceLink, type CreateLinkDto } from '../api/links'
import { isServiceLinkUrl } from '../utils/url'
import {
  useCreateLinkMutation, useUpdateLinkMutation, useDeleteLinkMutation,
  useUploadLinkIconMutation, useDeleteLinkIconMutation,
} from '../queries/admin'
import { parseApiError } from '../utils/parseApiError'
import { useConfirmDialog } from './useConfirmDialog'
import { useLinksStore } from '../stores/links'

/**
 * Icon-upload зависимость формы.
 * Передаётся снаружи (DI), чтобы LinksTab мог использовать один общий экземпляр
 * useLinkIconUpload (он же переиспользуется в LinkFormModal), а форма управляла
 * его reset/чтением в нужные моменты жизненного цикла.
 */
export interface LinkFormIconDeps {
  iconFile: Ref<File | null>
  iconRemoved: Ref<boolean>
  resetIconState: () => void
}

function emptyLinkForm(): CreateLinkDto {
  return {
    title: '',
    url: '',
    description: null,
    category: null,
    sort_order: 0,
    supports_sso: false,
    is_active: true,
    show_on_home: false,
    kb_url: null,
  }
}

/**
 * Состояние и CRUD-логика формы ссылки (модалка add/edit).
 * Server-state: мутации через TanStack Query (queries/admin).
 * Pinia store синхронизируется дополнительно — это устоявшийся в проекте паттерн
 * двойной источника истины для links (queries инвалидатируют кэш, store — для
 * не-query потребителей). См. audit M12.
 */
export function useLinkForm(icon: LinkFormIconDeps) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const store = useLinksStore()

  const createLinkMut = useCreateLinkMutation()
  const updateLinkMut = useUpdateLinkMutation()
  const deleteLinkMut = useDeleteLinkMutation()
  const uploadIconMut = useUploadLinkIconMutation()
  const deleteIconMut = useDeleteLinkIconMutation()

  const linkModalOpen = ref(false)
  const savingLink = ref(false)
  const editingLink = ref<ServiceLink | null>(null)
  const linkFormRef = ref<FormInst | null>(null)
  const linkForm = ref<CreateLinkDto>(emptyLinkForm())

  const linkRules = computed(() => ({
    title: [{ required: true, message: t('admin.links.form.required'), trigger: 'blur' }],
    url: [
      { required: true, message: t('admin.links.form.required'), trigger: 'blur' },
      {
        validator: (_: unknown, value: string) => isServiceLinkUrl(value),
        message: t('admin.links.form.invalidUrl'),
        trigger: 'blur',
      },
    ],
    kb_url: [
      {
        validator: (_: unknown, value: string) => !value || isServiceLinkUrl(value),
        message: t('admin.links.form.invalidUrl'),
        trigger: 'blur',
      },
    ],
  }))

  function openAddLink() {
    editingLink.value = null
    linkForm.value = emptyLinkForm()
    icon.resetIconState()
    linkModalOpen.value = true
  }

  function openEditLink(link: ServiceLink) {
    editingLink.value = link
    linkForm.value = {
      title: link.title,
      url: link.url,
      description: link.description,
      category: link.category,
      sort_order: link.sort_order,
      supports_sso: link.supports_sso,
      is_active: link.is_active,
      show_on_home: link.show_on_home,
      kb_url: link.kb_url,
    }
    icon.resetIconState()
    linkModalOpen.value = true
  }

  async function openDeleteLink(link: ServiceLink) {
    const ok = await confirm({
      title: t('admin.links.confirmDelete', { title: link.title }),
      content: t('admin.links.confirmDeleteHint'),
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      await deleteLinkMut.mutateAsync(link.id)
      store.removeLink(link.id)
      message.success(t('admin.links.deleted'))
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  async function submitLink() {
    try {
      await linkFormRef.value?.validate()
    } catch {
      return
    }
    savingLink.value = true
    try {
      const dto: CreateLinkDto = {
        title: linkForm.value.title,
        url: linkForm.value.url,
        description: linkForm.value.description || null,
        category: linkForm.value.category || null,
        sort_order: linkForm.value.sort_order ?? 0,
        supports_sso: linkForm.value.supports_sso,
        is_active: linkForm.value.is_active,
        show_on_home: linkForm.value.show_on_home,
        kb_url: linkForm.value.kb_url || null,
      }

      let saved: ServiceLink
      if (editingLink.value) {
        saved = await updateLinkMut.mutateAsync({ id: editingLink.value.id, dto })
        store.updateLinkItem(saved)
      } else {
        saved = await createLinkMut.mutateAsync(dto)
        store.addLink(saved)
      }

      if (icon.iconFile.value) {
        const withIcon = await uploadIconMut.mutateAsync({ id: saved.id, file: icon.iconFile.value })
        store.updateLinkItem(withIcon)
      } else if (icon.iconRemoved.value && editingLink.value?.icon_url) {
        await deleteIconMut.mutateAsync(saved.id)
        store.clearLinkIcon(saved.id)
      }

      message.success(t('admin.links.saved'))
      linkModalOpen.value = false
    } catch (e) {
      message.error(parseApiError(e, t))
    } finally {
      savingLink.value = false
    }
  }

  return {
    linkModalOpen,
    savingLink,
    editingLink,
    linkFormRef,
    linkForm,
    linkRules,
    openAddLink,
    openEditLink,
    openDeleteLink,
    submitLink,
  }
}

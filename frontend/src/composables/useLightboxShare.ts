import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, type SelectOption } from 'naive-ui'
import { createShareLink, createFolderShareLink } from '../api/photos'
import type { Photo } from '../api/photos'

export interface UseLightboxShareOptions {
  currentPhoto: () => Photo | null
  selectedFolderId: () => string | null
}

export function useLightboxShare(opts: UseLightboxShareOptions) {
  const { t } = useI18n()
  const message = useMessage()

  const shareModalOpen = ref(false)
  const shareExpiresInDays = ref<number | null>(7)
  const shareUrl = ref('')
  const creatingShare = ref(false)

  const folderShareModalOpen = ref(false)
  const folderShareExpiresInDays = ref<number | null>(7)
  const folderShareUrl = ref('')
  const creatingFolderShare = ref(false)

  const expiryOptions = computed(() => [
    { label: t('photos.lightbox.expires1d'), value: 1 },
    { label: t('photos.lightbox.expires7d'), value: 7 },
    { label: t('photos.lightbox.expires30d'), value: 30 },
    { label: t('photos.lightbox.expires90d'), value: 90 },
    { label: t('photos.lightbox.expiresNever'), value: null },
  ] as SelectOption[])

  async function copyToClipboard(text: string): Promise<boolean> {
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true }
      console.warn('[LightboxModal] navigator.clipboard unavailable, falling back to deprecated execCommand("copy")')
      const ta = document.createElement('textarea')
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
      document.body.appendChild(ta); ta.focus(); ta.select()
      const ok = document.execCommand('copy'); document.body.removeChild(ta); return ok
    } catch (err) {
      console.warn('[LightboxModal] copyToClipboard failed', err)
      return false
    }
  }

  function openShareModal() {
    shareUrl.value = ''
    shareExpiresInDays.value = 7
    shareModalOpen.value = true
  }

  async function generateShareLink() {
    const photo = opts.currentPhoto()
    if (!photo) return
    creatingShare.value = true
    try {
      const link = await createShareLink(photo.id, shareExpiresInDays.value)
      shareUrl.value = `${window.location.origin}/p/${link.token}`
      message.success(t('photos.lightbox.shareLinkCreated'))
    } catch { message.error(t('errors.generic')) }
    finally { creatingShare.value = false }
  }

  async function copyShareUrl() {
    const ok = await copyToClipboard(shareUrl.value)
    ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
  }

  function openFolderShareModal() {
    folderShareUrl.value = ''
    folderShareExpiresInDays.value = 7
    folderShareModalOpen.value = true
  }

  async function generateFolderShareLink() {
    const folderId = opts.selectedFolderId()
    if (!folderId) return
    creatingFolderShare.value = true
    try {
      const link = await createFolderShareLink(folderId, folderShareExpiresInDays.value)
      folderShareUrl.value = `${window.location.origin}/photos/public/${link.token}`
      message.success(t('photos.lightbox.shareLinkCreated'))
    } catch { message.error(t('errors.generic')) }
    finally { creatingFolderShare.value = false }
  }

  async function copyFolderShareUrl() {
    const ok = await copyToClipboard(folderShareUrl.value)
    ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
  }

  async function copyInPortalLink() {
    const p = opts.currentPhoto()
    if (!p) return
    const folderId = opts.selectedFolderId()
    const folderQ = folderId ? `folder=${folderId}&` : ''
    const url = `${window.location.origin}/photos?${folderQ}photo=${p.id}`
    const ok = await copyToClipboard(url)
    ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
  }

  return {
    shareModalOpen, shareExpiresInDays, shareUrl, creatingShare,
    folderShareModalOpen, folderShareExpiresInDays, folderShareUrl, creatingFolderShare,
    expiryOptions,
    openShareModal, generateShareLink, copyShareUrl,
    openFolderShareModal, generateFolderShareLink, copyFolderShareUrl,
    copyInPortalLink,
  }
}

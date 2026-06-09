import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ComposerTranslation } from 'vue-i18n'
import type { Router } from 'vue-router'
import { saveDraft } from '../../api/news'
import { parseApiError } from '../../utils/parseApiError'
import {
  useNewsDetailQuery, useCreateNewsMutation, useUpdateNewsMutation,
} from '../../queries/news'
import { useInterval } from '../../composables/useInterval'
import { useDirtyTracker } from '../../composables/useDirtyTracker'
import {
  type FocalPoint,
  AUTOSAVE_INTERVAL_MS,
  toFocalPoint, toNewsStatus,
  isoToMs, msToIso, formatSavedTime,
} from './newsFormMappers'

export function useNewsFormState(options: {
  isEdit: ComputedRef<boolean>
  newsId: ComputedRef<string | undefined>
  t: ComposerTranslation
  locale: Ref<string>
  message: { success: (s: string) => void; error: (s: string) => void }
  router: Router
}) {
  const { isEdit, newsId, t, locale, message, router } = options

  const formRef = ref()
  const saving = ref(false)
  const autoSaveInFlight = ref(false)
  const lastSaved = ref('')

  const form = ref({
    title: '',
    body: '',
    status: 'draft' as 'draft' | 'published',
    is_pinned: false,
    categories: [] as string[],
    publish_at: null as string | null,
    published_at: null as string | null,
    cover_focal_point: null as FocalPoint | null,
  })

  const coverImageUrl = ref<string | null>(null)

  const { isDirty, markPristine } = useDirtyTracker(() =>
    JSON.stringify({
      title: form.value.title,
      body: form.value.body,
      status: form.value.status,
      is_pinned: form.value.is_pinned,
      categories: form.value.categories,
      publish_at: form.value.publish_at,
      published_at: form.value.published_at,
      cover_focal_point: form.value.cover_focal_point,
    }),
  )

  const publishAtMs = computed({
    get: () => isoToMs(form.value.publish_at),
    set: (ms: number | null) => { form.value.publish_at = msToIso(ms) },
  })

  const publishedAtMs = computed({
    get: () => isoToMs(form.value.published_at),
    set: (ms: number | null) => { form.value.published_at = msToIso(ms) },
  })

  const { data: editNewsData, isLoading: loadingNews } = useNewsDetailQuery(
    computed(() => isEdit.value && !!newsId.value ? newsId.value! : ''),
  )

  const createNewsMutation = useCreateNewsMutation()
  const updateNewsMutation = useUpdateNewsMutation()

  const formInitialized = ref(false)
  watch(editNewsData, (news) => {
    if (news && !formInitialized.value) {
      formInitialized.value = true
      form.value.title = news.title
      form.value.body = news.body
      form.value.status = toNewsStatus(news.status)
      form.value.is_pinned = news.is_pinned
      form.value.categories = news.categories ?? []
      form.value.publish_at = news.publish_at
      form.value.published_at = news.published_at
      form.value.cover_focal_point = toFocalPoint(news.cover_focal_point)
      coverImageUrl.value = news.cover_image_url
      markPristine()
    }
  }, { immediate: true })

  markPristine()

  useInterval(async () => {
    if (saving.value || autoSaveInFlight.value) return
    if (isEdit.value && newsId.value && form.value.status === 'draft') {
      autoSaveInFlight.value = true
      try {
        await saveDraft(newsId.value, { title: form.value.title, body: form.value.body })
        lastSaved.value = formatSavedTime(new Date(), locale.value)
      } catch { /* ignore */ } finally {
        autoSaveInFlight.value = false
      }
    }
  }, AUTOSAVE_INTERVAL_MS, { immediate: true })

  async function validateForm(): Promise<boolean> {
    const fr = formRef.value
    if (!fr) return true
    try {
      await fr.validate()
      return true
    } catch {
      return false
    }
  }

  async function saveAsDraft() {
    if (!(await validateForm())) return
    saving.value = true
    try {
      const data = { ...form.value, status: 'draft' as const }
      if (isEdit.value && newsId.value) {
        await updateNewsMutation.mutateAsync({ id: newsId.value, dto: data })
        markPristine()
      } else {
        const created = await createNewsMutation.mutateAsync(data)
        if (!created?.id) throw new Error('createNews returned no id')
        markPristine()
        router.replace(`/news/${created.id}/edit`)
      }
      message.success(t('common.save'))
    } catch (e) {
      message.error(parseApiError(e, t))
    } finally {
      saving.value = false
    }
  }

  async function publish() {
    if (!(await validateForm())) return
    saving.value = true
    try {
      const data = { ...form.value, status: 'published' as const }
      if (isEdit.value && newsId.value) {
        await updateNewsMutation.mutateAsync({ id: newsId.value, dto: data })
      } else {
        const created = await createNewsMutation.mutateAsync(data)
        if (!created?.id) throw new Error('createNews returned no id')
      }
      markPristine()
      message.success(t('news.create.submit'))
      router.push('/news')
    } catch (e) {
      message.error(parseApiError(e, t))
    } finally {
      saving.value = false
    }
  }

  return {
    form,
    coverImageUrl,
    publishAtMs,
    publishedAtMs,
    formRef,
    saving,
    lastSaved,
    editNewsData,
    loadingNews,
    isDirty,
    markPristine,
    saveAsDraft,
    publish,
  }
}

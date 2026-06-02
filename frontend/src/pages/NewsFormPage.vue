<template>
  <div class="form-wrap">
    <header class="form-head">
      <h1 class="u-page-head__title">
        {{ isEdit ? t('news.edit.title') : t('news.create.title') }}
      </h1>
      <div class="u-page-head__sub">
        {{ t('news.pageSub') }}
      </div>
    </header>

    <n-spin
      v-if="loadingNews"
      style="margin:40px auto;display:block"
    />

    <n-form
      v-else
      ref="formRef"
      :model="form"
      :rules="rules"
      label-placement="top"
    >
      <div class="form-grid">
        <div class="form-main">
          <NewsFormMainFields
            v-model:title="form.title"
            v-model:body="form.body"
            :upload-endpoint="newsId ? `/api/v1/news/${newsId}/inline-media` : undefined"
          />

          <NewsGalleryPanel :news-id="newsId" />
          <NewsAttachmentsPanel :news-id="newsId" />
          <NewsPollPanel
            :news-id="newsId"
            :has-poll="editNewsData?.has_poll"
          />
        </div>

        <aside class="form-side">
          <NewsFormSettingsCard
            v-model:cover-image-url="coverImageUrl"
            v-model:focal-point="form.cover_focal_point"
            v-model:status="form.status"
            v-model:categories="form.categories"
            v-model:is-pinned="form.is_pinned"
            v-model:publish-at-ms="publishAtMs"
            v-model:published-at-ms="publishedAtMs"
            :news-id="newsId"
            :is-edit="isEdit"
            :cover-max-size-mb="coverMaxSizeMb"
            :status-options="statusOptions"
            :category-options="categoryOptions"
            :saving="saving"
            :last-saved="lastSaved"
            @save-draft="saveAsDraft"
            @publish="publish"
            @cancel="router.back()"
          />
        </aside>
      </div>
    </n-form>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NForm, NSpin, useMessage } from 'naive-ui'
import NewsGalleryPanel from '../components/NewsGalleryPanel.vue'
import NewsAttachmentsPanel from '../components/NewsAttachmentsPanel.vue'
import NewsPollPanel from '../components/news/poll-panel/NewsPollPanel.vue'
import NewsFormMainFields from '../components/news/NewsFormMainFields.vue'
import NewsFormSettingsCard from '../components/news/NewsFormSettingsCard.vue'
import { useNewsFormState } from './composables/useNewsFormState'
import { useNewsFormOptions } from './composables/useNewsFormOptions'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const message = useMessage()

const isEdit = computed(() => !!route.params.id)
const newsId = computed(() => route.params.id as string | undefined)

const {
  form, coverImageUrl, publishAtMs, publishedAtMs,
  formRef, saving, lastSaved, editNewsData, loadingNews,
  saveAsDraft, publish,
} = useNewsFormState({ isEdit, newsId, t, locale, message, router })

const { categoryOptions, coverMaxSizeMb, statusOptions } = useNewsFormOptions(t)

const rules = {
  title: [{ required: true, message: t('news.form.required'), trigger: 'blur' }],
}
</script>

<style scoped>
.form-wrap {
  max-width: 1280px;
  margin: 0 auto;
}
.form-head {
  margin-bottom: 20px;
}
.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: flex-start;
}
.form-main { min-width: 0; }
.form-side { min-width: 0; }
@media (max-width: 1100px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>

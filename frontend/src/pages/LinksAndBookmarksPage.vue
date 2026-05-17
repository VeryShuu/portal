<template>
  <div class="links-wrap">
    <header class="page-head u-page-head">
      <div>
        <h1 class="u-page-head__title">
          {{ t('nav.links') }}
        </h1>
        <p class="u-page-head__sub">
          {{ t('links.pageSub') }}
        </p>
      </div>
      <n-button
        v-if="activeTab === 'corporate' && auth.isAdmin"
        type="primary"
        @click="serviceTab?.openAdd()"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('admin.links.add') }}
      </n-button>
      <n-button
        v-else-if="activeTab === 'my'"
        type="primary"
        @click="bookmarksTab?.openAdd()"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('bookmarks.add') }}
      </n-button>
    </header>

    <n-tabs
      :value="activeTab"
      type="line"
      animated
      style="margin-bottom: 24px"
      @update:value="setTab"
    >
      <n-tab name="corporate">
        {{ t('links.tabs.corporate') }}
      </n-tab>
      <n-tab name="my">
        {{ t('links.tabs.my') }}
      </n-tab>
    </n-tabs>

    <ServiceLinksTab
      v-show="activeTab === 'corporate'"
      ref="serviceTab"
    />
    <BookmarksTab
      v-show="activeTab === 'my'"
      ref="bookmarksTab"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NTabs, NTab } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import ServiceLinksTab from '../components/links/ServiceLinksTab.vue'
import BookmarksTab from '../components/links/BookmarksTab.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const auth = useAuthStore()

const activeTab = computed(() =>
  (route.query.tab as string) === 'my' ? 'my' : 'corporate',
)

function setTab(val: string) {
  router.replace({ query: val === 'my' ? { tab: 'my' } : {} })
}

const serviceTab = ref<InstanceType<typeof ServiceLinksTab>>()
const bookmarksTab = ref<InstanceType<typeof BookmarksTab>>()
</script>

<style scoped>
.links-wrap {
  max-width: 1200px;
  margin: 0 auto;
}
.page-head {
  margin-bottom: 24px;
  align-items: flex-start;
}
@media (max-width: 640px) {
  .page-head { flex-direction: column; align-items: stretch; }
}
</style>

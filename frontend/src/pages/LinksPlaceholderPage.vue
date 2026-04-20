<template>
  <AppLayout>
    <template #header-title><span>{{ t('nav.links') }}</span></template>

    <div class="links-wrap">
      <n-spin v-if="store.loadingLinks" />
      <template v-else>
        <div v-if="!Object.keys(store.groupedLinks).length">
          <n-empty :description="t('links.empty')" style="margin-top: 60px" />
        </div>

        <template v-for="(group, category) in store.groupedLinks" :key="category">
          <div class="category-section">
            <h3 class="category-title">{{ category }}</h3>
            <div class="links-grid">
              <div
                v-for="link in group"
                :key="link.id"
                class="link-card"
                @click="store.openLink(link)"
              >
                <div class="link-icon">
                  <img v-if="link.icon_url" :src="link.icon_url" :alt="link.title" />
                  <n-icon v-else size="28"><LinkOutline /></n-icon>
                </div>
                <div class="link-info">
                  <div class="link-title">{{ link.title }}</div>
                  <div v-if="link.description" class="link-desc">{{ link.description }}</div>
                </div>
                <n-icon v-if="link.supports_sso" size="14" class="sso-badge" title="SSO">
                  <ShieldCheckmarkOutline />
                </n-icon>
              </div>
            </div>
          </div>
        </template>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NEmpty, NSpin, NIcon } from 'naive-ui'
import { LinkOutline, ShieldCheckmarkOutline } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import { useLinksStore } from '../stores/links'

const { t } = useI18n()
const store = useLinksStore()

onMounted(() => store.loadLinks())
</script>

<style scoped>
.links-wrap {
  max-width: 1100px;
  margin: 0 auto;
}
.category-section {
  margin-bottom: 32px;
}
.category-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 12px;
  color: var(--n-text-color-2, #888);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.links-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.link-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color, #e0e0e0);
  cursor: pointer;
  position: relative;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.link-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  border-color: var(--n-primary-color, #18a058);
}
.link-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.link-icon img {
  width: 32px;
  height: 32px;
  object-fit: contain;
}
.link-info {
  flex: 1;
  min-width: 0;
}
.link-title {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-desc {
  font-size: 12px;
  color: var(--n-text-color-3, #aaa);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sso-badge {
  flex-shrink: 0;
  color: #18a058;
  opacity: 0.7;
}
</style>

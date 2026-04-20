<template>
  <n-layout>
    <n-layout-header bordered>
      <div class="header-inner">
        <span class="logo">{{ t('app.title') }}</span>
      </div>
    </n-layout-header>
    <n-layout-content>
      <n-spin v-if="loading" />
      <n-empty v-else :description="t('home.empty')" />
    </n-layout-content>
  </n-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NLayout, NLayoutHeader, NLayoutContent, NSpin, NEmpty } from 'naive-ui'

const { t } = useI18n()
const loading = ref(false)
</script>

<style scoped>
.header-inner {
  display: flex;
  align-items: center;
  padding: 0 24px;
  height: 64px;
}
.logo {
  font-size: 18px;
  font-weight: 600;
}
</style>

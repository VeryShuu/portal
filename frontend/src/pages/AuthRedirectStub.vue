<template>
  <div />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

onMounted(() => {
  const rawRedirect = (route.query.redirect as string) || '/'
  const SAFE = /^\/(?![/\\])[A-Za-z0-9_\-./?#&=%@:+,~!]*$/
  const redirectTo = rawRedirect && SAFE.test(rawRedirect)
    && !rawRedirect.startsWith('/api/')
    && !rawRedirect.startsWith('/realms/')
    ? rawRedirect
    : '/'
  window.location.replace('/api/v1/auth/login?redirect=' + encodeURIComponent(redirectTo))
})
</script>

<script setup lang="ts">
// Public marketing site — no auth required.
// Keeps the browser tab title in sync with both the current route and the
// active locale (so switching ar <-> en also updates the tab title).
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

const { t, locale } = useI18n()
const route = useRoute()

function updateTitle() {
  const titleKey = route.meta.titleKey as string | undefined
  const brand = locale.value === 'ar' ? t('marketing.brand.nameNative') : t('marketing.brand.name')
  document.title = titleKey ? `${t(titleKey)} | ${brand}` : brand
}

watch([() => route.meta.titleKey, locale], updateTitle, { immediate: true })
</script>

<template>
  <RouterView />
</template>

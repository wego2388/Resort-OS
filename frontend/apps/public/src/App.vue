<script setup lang="ts">
// Public marketing site — no auth required.
// Keeps <title>, meta description, Open Graph tags, canonical and hreflang
// links in sync with both the current route and the active locale.
import { useSEO } from './composables/useSEO'

useSEO()
</script>

<template>
  <RouterView />
</template>

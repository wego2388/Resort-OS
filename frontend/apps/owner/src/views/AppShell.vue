<script setup lang="ts">
/**
 * AppShell — الغلاف الرئيسي للـ owner app.
 * - Safe area top/bottom (iPhone notch/Dynamic Island)
 * - Bottom navigation (Now + Performance)
 * - RouterView في المنتصف
 */
import { computed } from 'vue'
import { useRoute, RouterView } from 'vue-router'

const route = useRoute()

const navItems = [
  { name: 'now',         label: 'الآن',   icon: '⚡' },
  { name: 'performance', label: 'الأداء', icon: '📊' },
] as const

const activeNav = computed(() => route.name as string)

function vibrate(ms = 6) {
  try { navigator.vibrate?.(ms) } catch { /* unsupported */ }
}
</script>

<template>
  <div class="flex flex-col h-dvh bg-owner-bg" style="padding-top: env(safe-area-inset-top)">
    <!-- Header -->
    <header class="flex items-center justify-between px-4 py-3 bg-owner-card border-b border-owner-border shrink-0">
      <h1 class="text-sm font-bold text-owner-text">المالك</h1>
      <div class="text-xs text-owner-muted">
        {{ new Date().toLocaleDateString('ar-EG', { weekday: 'long', day: 'numeric', month: 'short' }) }}
      </div>
    </header>

    <!-- Main content -->
    <main class="flex-1 flex flex-col overflow-hidden">
      <RouterView />
    </main>

    <!-- Bottom navigation -->
    <nav class="bottom-nav" role="navigation" aria-label="التنقل الرئيسي">
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="`/${item.name}`"
        class="bottom-nav-item"
        :class="{ active: activeNav === item.name }"
        :aria-current="activeNav === item.name ? 'page' : undefined"
        @click="vibrate()"
      >
        <span class="text-xl leading-none" aria-hidden="true">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

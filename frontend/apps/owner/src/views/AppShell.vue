<script setup lang="ts">
/**
 * AppShell — الغلاف الرئيسي للـ owner app.
 * - Safe area top/bottom (iPhone notch/Dynamic Island)
 * - Bottom navigation (Now + Performance + Sales + Expenses + Shifts + HR)
 * - Logout button في الـ header (Decision 0004 §7b)
 * - RouterView في المنتصف
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import { useAuthStore } from '@resort-os/core'

const route  = useRoute()
const router = useRouter()
const auth   = useAuthStore()

const navItems = [
  { name: 'now',         label: 'الآن',       icon: '⚡' },
  { name: 'performance', label: 'الأداء',     icon: '📊' },
  { name: 'sales',       label: 'المبيعات',   icon: '🛒' },
  { name: 'expenses',    label: 'المصروفات',  icon: '💰' },
  { name: 'shifts',      label: 'الورديات',   icon: '🔔' },
  { name: 'hr',          label: 'الموظفين',   icon: '👥' },
] as const

const activeNav = computed(() => route.name as string)

const loggingOut = ref(false)

async function handleLogout() {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await auth.logout()
  } finally {
    loggingOut.value = false
  }
  router.replace('/login')
}

function vibrate(ms = 6) {
  try { navigator.vibrate?.(ms) } catch { /* unsupported */ }
}
</script>

<template>
  <div class="flex flex-col h-dvh bg-owner-bg" style="padding-top: env(safe-area-inset-top)">
    <!-- Header -->
    <header class="flex items-center justify-between px-4 py-3 bg-owner-card border-b border-owner-border shrink-0">
      <h1 class="text-sm font-bold text-owner-text">المالك</h1>
      <div class="flex items-center gap-3">
        <div class="text-xs text-owner-muted">
          {{ new Date().toLocaleDateString('ar-EG', { weekday: 'long', day: 'numeric', month: 'short' }) }}
        </div>
        <!-- Logout — أمان أساسي (Decision 0004 §7b) -->
        <button
          class="text-xs text-owner-muted hover:text-owner-red active:text-owner-red transition-colors touch-target px-1"
          :disabled="loggingOut"
          aria-label="تسجيل الخروج"
          @click="handleLogout"
        >
          <span v-if="loggingOut">...</span>
          <span v-else>خروج</span>
        </button>
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
        <span class="text-lg leading-none" aria-hidden="true">{{ item.icon }}</span>
        <span class="text-[10px]">{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

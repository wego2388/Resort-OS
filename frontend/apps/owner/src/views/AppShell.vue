<script setup lang="ts">
/**
 * AppShell — الغلاف الرئيسي للـ owner app.
 * - Safe area top/bottom (iPhone notch/Dynamic Island)
 * - Bottom navigation (Now + Performance + Sales + Expenses + Shifts + HR)
 * - Logout button في الـ header (Decision 0004 §7b)
 * - Theme toggle + text-size control في الـ header (2026-08-17، طلب محمد
 *   الصريح بعد تجربة حقيقية: نص/أرقام صغيرة وهو لابس نظارة قراءة)
 * - RouterView في المنتصف
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import { useAuthStore } from '@resort-os/core'
import { ThemeToggle, AppIcon, type IconName } from '@resort-os/ui'
import SearchOverlay from '../components/SearchOverlay.vue'
import { useTextScale } from '../composables/useTextScale'

const route  = useRoute()
const router = useRouter()
const auth   = useAuthStore()
const { cycleScale, label: textScaleLabel } = useTextScale()

const searchOpen = ref(false)
const activeTitle = computed(() => String(route.meta.title || 'نظرة المالك'))

// 2026-08-19: استبدال الإيموجي بأيقونات SVG حقيقية من الـDesign System —
// طلب محمد الصريح ("شريط الأيقونات محتاج يكبر أو طريقة عرض أفضل"). فايدة
// إضافية حقيقية مش بصرية بس: الإيموجي بتتجاهل CSS `color` تمامًا (بتحتفظ
// بألوانها الأصلية دايمًا)، يعني حالة "active" (اللون الأخضر) كانت بتأثر
// على النص بس مش الأيقونة نفسها من الأساس. أيقونات SVG بتورث اللون فعليًا
// عبر currentColor، فحالة active بقت شغالة على الأيقونة والنص مع بعض.
const navItems: ReadonlyArray<{ name: string; label: string; icon: IconName }> = [
  { name: 'now',         label: 'الآن',       icon: 'bolt' },
  { name: 'performance', label: 'الأداء',     icon: 'chart' },
  { name: 'sales',       label: 'المبيعات',   icon: 'cart' },
  { name: 'expenses',    label: 'المصروفات',  icon: 'cash' },
  { name: 'shifts',      label: 'الورديات',   icon: 'bell' },
  { name: 'hr',          label: 'الموظفين',   icon: 'users' },
]

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
    <header class="owner-header flex items-center justify-between gap-3 px-4 py-2 bg-owner-card border-b border-owner-border shrink-0">
      <div class="min-w-0">
        <div class="truncate text-[10px] font-semibold tracking-wide text-owner-green">El Kheima Beach Resort</div>
        <h1 class="truncate text-sm font-bold text-owner-text">{{ activeTitle }}</h1>
      </div>
      <div class="flex items-center gap-3">
        <div class="text-xs text-owner-muted hidden sm:block">
          {{ new Date().toLocaleDateString('ar-EG', { weekday: 'long', day: 'numeric', month: 'short' }) }}
        </div>
        <!-- بحث عام — يشوف أي صنف/منتج/مورد/مصروف/موظف -->
        <button
          class="touch-target text-owner-muted active:text-owner-green transition-colors"
          aria-label="بحث"
          @click="searchOpen = true"
        >
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="7" />
            <path stroke-linecap="round" d="M21 21l-4.35-4.35" />
          </svg>
        </button>
        <!-- حجم النص — عادي/كبير/أكبر (طلب محمد الصريح 2026-08-17) -->
        <button
          class="touch-target text-owner-muted active:text-owner-green transition-colors text-xs font-bold"
          :aria-label="`حجم النص: ${textScaleLabel()} — اضغط للتغيير`"
          :title="`حجم النص: ${textScaleLabel()}`"
          @click="cycleScale"
        >Aa</button>
        <!-- الوضع الليلي/النهاري (طلب محمد الصريح 2026-08-17) -->
        <ThemeToggle
          light-label="التبديل للوضع الفاتح"
          dark-label="التبديل للوضع الداكن"
        />
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

    <SearchOverlay :open="searchOpen" @close="searchOpen = false" />

    <!-- Main content -->
    <main class="owner-main flex-1 flex flex-col overflow-hidden">
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
        <AppIcon :name="item.icon" size="lg" />
        <span class="bottom-nav-label">{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

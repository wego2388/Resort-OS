/**
 * useOwnerData — fetches /owner/now + /owner/performance with:
 * - auto-refresh كل 60 ثانية (Now screen) / 5 دقائق (Performance screen)
 * - pull-to-refresh بـ useSwipe من @vueuse/core
 * - visibility-based refresh: عند عودة المستخدم للتطبيق
 * - loading/error state
 * - لا caching — بيانات مالية حساسة (Decision 0004)
 */
import { ref, onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { useSwipe } from '@vueuse/core'
import { fetchOwnerNow, fetchOwnerPerformance } from '../api/owner'
import type { OwnerNowResponse, OwnerPerformanceResponse } from '../api/types'

const NOW_REFRESH_MS         = 60_000       // 60 ثانية — Now screen
const PERFORMANCE_REFRESH_MS = 5 * 60_000  // 5 دقائق — Performance screen

export function useOwnerNow(scrollContainer: Ref<HTMLElement | null>) {
  const data       = ref<OwnerNowResponse | null>(null)
  const loading    = ref(true)
  const error      = ref<string | null>(null)
  const refreshing = ref(false)

  let timer: ReturnType<typeof setInterval> | null = null

  async function load(silent = false) {
    if (!silent) loading.value = true
    error.value = null
    try {
      data.value = await fetchOwnerNow()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'خطأ في جلب البيانات'
    } finally {
      loading.value  = false
      refreshing.value = false
    }
  }

  // Pull-to-refresh: swipe down من أعلى الصفحة
  useSwipe(scrollContainer, {
    onSwipeEnd(_e, direction) {
      if (
        direction === 'down' &&
        (scrollContainer.value?.scrollTop ?? 0) === 0 &&
        !refreshing.value
      ) {
        refreshing.value = true
        navigator.vibrate?.(10)
        load(true)
      }
    },
  })

  // Visibility refresh: عند عودة المستخدم من خلفية التطبيق
  function onVisibilityChange() {
    if (document.visibilityState === 'visible') load(true)
  }

  onMounted(() => {
    load()
    timer = setInterval(() => load(true), NOW_REFRESH_MS)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { data, loading, error, refreshing, reload: () => load(true) }
}

export function useOwnerPerformance() {
  const data    = ref<OwnerPerformanceResponse | null>(null)
  const loading = ref(true)
  const error   = ref<string | null>(null)

  let timer: ReturnType<typeof setInterval> | null = null

  async function load(silent = false) {
    if (!silent) loading.value = true
    error.value = null
    try {
      data.value = await fetchOwnerPerformance()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'خطأ في جلب البيانات'
    } finally {
      loading.value = false
    }
  }

  // Visibility refresh: عند العودة للتطبيق
  function onVisibilityChange() {
    if (document.visibilityState === 'visible') load(true)
  }

  onMounted(() => {
    load()
    timer = setInterval(() => load(true), PERFORMANCE_REFRESH_MS)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { data, loading, error, reload: () => load(true) }
}

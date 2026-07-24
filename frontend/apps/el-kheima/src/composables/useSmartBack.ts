/**
 * useSmartBack — زر "رجوع" ذكي يتعامل مع 3 حالات:
 *
 *  1. المستخدم جاء من داخل التطبيق (history.length > 1)  → router.back()
 *  2. فتح الصفحة مباشرة (deep link / refresh)             → يروح للـ fallback
 *  3. مش authenticated خالص                              → يروح للـ fallback
 *
 * الاستخدام:
 *   const { goBack } = useSmartBack()          // fallback = home الخاص بالدور
 *   const { goBack } = useSmartBack('/portal/profile')  // fallback محدد
 */
import { useRouter } from 'vue-router'
import { useAuthStore } from '@resort-os/core'
import { homeRouteFor } from '../router/index'

export function useSmartBack(fallback?: string) {
  const router = useRouter()
  const auth = useAuthStore()

  function goBack() {
    const target = fallback ?? homeRouteFor(auth.role)
    // window.history.length === 1 يعني مفيش تاريخ — الصفحة اتفتحت مباشرة
    if (window.history.length > 1) {
      router.back()
    } else {
      router.push(target)
    }
  }

  return { goBack }
}

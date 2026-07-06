<script setup lang="ts">
// مسح QR لتسجيل دخول فوري لحجز شاطئ — يعرض بيانات الحجز فوراً (بدون تسجيل دخول)،
// وبيطلب تسجيل دخول الكاشير فقط عند تأكيد الدخول الفعلي (لأنه بيستهلك سعة/فوط حقيقية).
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, useAuthStore } from '@resort-os/core'

const route = useRoute()
const reservationId = computed(() => Number(route.params.reservationId))
const auth = useAuthStore()

interface ReservationPublic {
  id: number
  guest_name: string
  guests_count: number
  with_towel: boolean
  reservation_date: string
  status: string
  total_amount: string | number
}

const reservation = ref<ReservationPublic | null>(null)
const loading = ref(true)
const notFound = ref(false)

const email = ref('')
const password = ref('')
const loginError = ref('')
const loggingIn = ref(false)

const checkingIn = ref(false)
const checkinError = ref('')
const checkedIn = ref(false)

const statusLabel: Record<string, string> = {
  pending: 'بانتظار الدخول',
  confirmed: 'مؤكد — بانتظار الدخول',
  checked_in: 'تم تسجيل الدخول ✅',
  no_show: 'لم يحضر',
  cancelled: 'ملغى',
}

async function fetchReservation() {
  loading.value = true
  notFound.value = false
  try {
    const { data } = await api.get(`/api/v1/beach/reservations/${reservationId.value}/public`)
    reservation.value = data
  } catch (e) {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

async function doLogin() {
  loginError.value = ''
  loggingIn.value = true
  try {
    await auth.login(email.value, password.value)
  } catch (e) {
    loginError.value = 'بيانات الدخول غير صحيحة'
  } finally {
    loggingIn.value = false
  }
}

async function confirmCheckin() {
  checkinError.value = ''
  checkingIn.value = true
  try {
    const { data } = await api.post(`/api/v1/beach/reservations/${reservationId.value}/checkin`)
    reservation.value = data
    checkedIn.value = true
  } catch (e: any) {
    checkinError.value = e?.response?.data?.detail ?? 'تعذّر تسجيل الدخول'
  } finally {
    checkingIn.value = false
  }
}

onMounted(fetchReservation)
</script>

<template>
  <div dir="rtl" class="min-h-screen bg-resort-bg flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl p-6 shadow-sm border border-resort-border max-w-sm w-full">

      <div v-if="loading" class="text-center py-10 text-gray-400">
        <div class="text-4xl mb-3">🏖️</div>
        <p>جاري التحميل...</p>
      </div>

      <div v-else-if="notFound" class="text-center py-8">
        <div class="text-4xl mb-3">❌</div>
        <p class="font-bold text-gray-800">الحجز غير موجود</p>
        <p class="text-sm text-gray-400 mt-1">تأكد من رمز QR الصحيح</p>
      </div>

      <template v-else-if="reservation">
        <div class="text-center mb-5">
          <div class="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-3 text-3xl">
            🏖️
          </div>
          <h1 class="text-lg font-black text-gray-900">تسجيل دخول الشاطئ</h1>
          <p class="text-xs text-gray-400">حجز رقم #{{ reservation.id }}</p>
        </div>

        <div class="bg-resort-bg rounded-xl p-4 mb-5 space-y-2 text-sm">
          <div class="flex justify-between"><span class="text-gray-500">الاسم</span><span class="font-bold text-gray-900">{{ reservation.guest_name }}</span></div>
          <div class="flex justify-between"><span class="text-gray-500">عدد الأفراد</span><span class="font-bold text-gray-900">{{ reservation.guests_count }}</span></div>
          <div class="flex justify-between"><span class="text-gray-500">فوطة</span><span class="font-bold text-gray-900">{{ reservation.with_towel ? 'نعم' : 'لا' }}</span></div>
          <div class="flex justify-between"><span class="text-gray-500">التاريخ</span><span class="font-bold text-gray-900">{{ reservation.reservation_date }}</span></div>
          <div class="flex justify-between"><span class="text-gray-500">الإجمالي</span><span class="font-bold text-gray-900">{{ reservation.total_amount }} EGP</span></div>
          <div class="flex justify-between pt-2 border-t border-resort-border">
            <span class="text-gray-500">الحالة</span>
            <span class="font-bold" :class="reservation.status === 'checked_in' ? 'text-green-600' : 'text-amber-600'">
              {{ statusLabel[reservation.status] ?? reservation.status }}
            </span>
          </div>
        </div>

        <!-- Already checked in -->
        <div v-if="reservation.status === 'checked_in'" class="text-center py-4">
          <div class="text-4xl mb-2">✅</div>
          <p class="font-bold text-green-700">تم تسجيل الدخول</p>
        </div>

        <!-- Blocked states -->
        <div v-else-if="['cancelled', 'no_show'].includes(reservation.status)" class="text-center py-4 text-gray-500 text-sm">
          لا يمكن تسجيل الدخول لهذا الحجز.
        </div>

        <!-- Needs cashier login before confirming -->
        <div v-else-if="!auth.isAuthenticated" class="space-y-3">
          <p class="text-xs text-gray-400 text-center mb-1">سجّل دخول الكاشير لتأكيد الدخول</p>
          <input v-model="email" type="email" placeholder="البريد الإلكتروني"
                 class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          <input v-model="password" type="password" placeholder="كلمة المرور"
                 class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          <p v-if="loginError" class="text-red-600 text-xs text-center">{{ loginError }}</p>
          <button @click="doLogin" :disabled="loggingIn"
                  class="w-full bg-primary text-white font-bold py-2.5 rounded-xl text-sm disabled:opacity-50">
            {{ loggingIn ? '...جاري الدخول' : 'تسجيل الدخول' }}
          </button>
        </div>

        <!-- Confirm check-in -->
        <div v-else class="space-y-3">
          <p v-if="checkinError" class="text-red-600 text-xs text-center">{{ checkinError }}</p>
          <button @click="confirmCheckin" :disabled="checkingIn"
                  class="w-full bg-gold text-white font-black py-3 rounded-xl text-base disabled:opacity-50">
            {{ checkingIn ? '...جاري التأكيد' : '✅ تأكيد تسجيل الدخول' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

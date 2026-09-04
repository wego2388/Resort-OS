<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@resort-os/core'

type Phase = 'identify' | 'otp' | 'portal'
type PortalConfig = { resort_name: string; terms_version: string; booking_rules_version: string }
type Contract = {
  id: number; contract_number: string; customer_name: string; room_type: string
  week_number: number | null; nights_per_year: number; season: string; status: string
  booking_frozen: boolean; start_date: string; end_date: string | null; unit_number: string | null
}
type Payment = { id: number; due_date: string; amount: string; paid_amount: string; status: string }
type VisitRequest = {
  id: number; preferred_start: string; preferred_end: string; status: string
  rejection_reason: string | null; created_at: string
}
type Reply = { id: number; author_type: string; message: string; created_at: string }
type Ticket = { id: number; subject: string; status: string; created_at: string; replies: Reply[] }

const TOKEN_KEY = 'resort-os:timeshare-owner-token'
const phase = ref<Phase>('identify')
const config = ref<PortalConfig | null>(null)
const contractNumber = ref('')
const phone = ref('')
const otpCode = ref('')
const ownerToken = ref(sessionStorage.getItem(TOKEN_KEY) ?? '')
const busy = ref(false)
const error = ref('')
const message = ref('')

const contract = ref<Contract | null>(null)
const installments = ref<Payment[]>([])
const maintenanceDues = ref<Payment[]>([])
const visits = ref<VisitRequest[]>([])
const tickets = ref<Ticket[]>([])
const activeSection = ref<'contract' | 'payments' | 'visits' | 'support'>('contract')

const visitForm = reactive({ preferred_start: '', preferred_end: '', notes: '', accepted: false })
const ticketForm = reactive({ subject: '', message: '' })
const replyText = reactive<Record<number, string>>({})

const ownerHeaders = computed(() => ({ 'X-Timeshare-Owner-Token': ownerToken.value }))

function apiMessage(exception: unknown, fallback: string): string {
  const detail = (exception as { response?: { data?: { detail?: string | { message?: string } } } }).response?.data?.detail
  return (typeof detail === 'object' ? detail?.message : detail) || fallback
}

function money(value: string | number | null | undefined): string {
  return new Intl.NumberFormat('ar-EG', { style: 'currency', currency: 'EGP', maximumFractionDigits: 2 })
    .format(Number(value ?? 0))
}

function dateLabel(value: string | null | undefined): string {
  return value ? new Intl.DateTimeFormat('ar-EG', { dateStyle: 'medium' }).format(new Date(value)) : '—'
}

async function requestOtp() {
  if (!contractNumber.value.trim() || !phone.value.trim()) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    const { data } = await api.post('/api/v1/timeshare/public/verify-request', {
      contract_number: contractNumber.value.trim(), phone: phone.value.trim(),
    })
    message.value = data?.message ?? 'لو البيانات صحيحة، وصلك كود التحقق على واتساب.'
    phase.value = 'otp'
  } catch (exception: unknown) {
    error.value = apiMessage(exception, 'تعذر إرسال كود التحقق. حاول بعد قليل.')
  } finally { busy.value = false }
}

async function confirmOtp() {
  if (!otpCode.value.trim()) return
  busy.value = true; error.value = ''
  try {
    const { data } = await api.post('/api/v1/timeshare/public/verify-confirm', {
      contract_number: contractNumber.value.trim(), otp_code: otpCode.value.trim(),
    })
    ownerToken.value = data.token
    sessionStorage.setItem(TOKEN_KEY, data.token)
    await loadPortal()
  } catch (exception: unknown) {
    error.value = apiMessage(exception, 'كود التحقق غير صحيح أو انتهت صلاحيته.')
  } finally { busy.value = false }
}

async function loadPortal() {
  if (!ownerToken.value) return
  busy.value = true; error.value = ''
  try {
    const [contractRes, paymentsRes, visitsRes, ticketsRes] = await Promise.all([
      api.get('/api/v1/timeshare/public/my-contract', { headers: ownerHeaders.value }),
      api.get('/api/v1/timeshare/public/my-payments', { headers: ownerHeaders.value }),
      api.get('/api/v1/timeshare/public/visit-requests', { headers: ownerHeaders.value }),
      api.get('/api/v1/timeshare/public/support-tickets', { headers: ownerHeaders.value }),
    ])
    contract.value = contractRes.data
    installments.value = paymentsRes.data.installments ?? []
    maintenanceDues.value = paymentsRes.data.maintenance_dues ?? []
    visits.value = visitsRes.data ?? []
    tickets.value = ticketsRes.data ?? []
    phase.value = 'portal'
  } catch (exception: unknown) {
    sessionStorage.removeItem(TOKEN_KEY)
    ownerToken.value = ''
    phase.value = 'identify'
    error.value = apiMessage(exception, 'انتهت الجلسة. تحقق من هويتك مرة أخرى.')
  } finally { busy.value = false }
}

async function downloadContract() {
  try {
    const { data } = await api.get('/api/v1/timeshare/public/my-contract/pdf', {
      headers: ownerHeaders.value, responseType: 'blob',
    })
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url; link.download = `timeshare-${contract.value?.contract_number ?? 'contract'}.pdf`; link.click()
    URL.revokeObjectURL(url)
  } catch (exception: unknown) { error.value = apiMessage(exception, 'تعذر تحميل العقد.') }
}

async function submitVisit() {
  if (!config.value || !visitForm.accepted || !visitForm.preferred_start || !visitForm.preferred_end) return
  busy.value = true; error.value = ''
  try {
    const { data } = await api.post('/api/v1/timeshare/public/visit-requests', {
      preferred_start: visitForm.preferred_start,
      preferred_end: visitForm.preferred_end,
      notes: visitForm.notes.trim() || null,
      terms_accepted: true,
      terms_version: config.value.terms_version,
      booking_rules_accepted: true,
      booking_rules_version: config.value.booking_rules_version,
    }, { headers: ownerHeaders.value })
    visits.value = [data, ...visits.value]
    Object.assign(visitForm, { preferred_start: '', preferred_end: '', notes: '', accepted: false })
    message.value = 'تم إرسال طلب الزيارة للمراجعة.'
  } catch (exception: unknown) { error.value = apiMessage(exception, 'تعذر إرسال طلب الزيارة.') }
  finally { busy.value = false }
}

async function submitTicket() {
  if (ticketForm.subject.trim().length < 3 || ticketForm.message.trim().length < 3) return
  busy.value = true; error.value = ''
  try {
    const { data } = await api.post('/api/v1/timeshare/public/support-tickets', {
      subject: ticketForm.subject.trim(), message: ticketForm.message.trim(),
    }, { headers: ownerHeaders.value })
    tickets.value = [data, ...tickets.value]
    Object.assign(ticketForm, { subject: '', message: '' })
    message.value = 'تم فتح تذكرة خدمة العملاء.'
  } catch (exception: unknown) { error.value = apiMessage(exception, 'تعذر فتح التذكرة.') }
  finally { busy.value = false }
}

async function reply(ticket: Ticket) {
  const text = (replyText[ticket.id] ?? '').trim()
  if (!text) return
  try {
    const { data } = await api.post(`/api/v1/timeshare/public/support-tickets/${ticket.id}/reply`,
      { message: text }, { headers: ownerHeaders.value })
    tickets.value = tickets.value.map(item => item.id === ticket.id ? data : item)
    replyText[ticket.id] = ''
  } catch (exception: unknown) { error.value = apiMessage(exception, 'تعذر إرسال الرد.') }
}

function logoutPortal() {
  sessionStorage.removeItem(TOKEN_KEY); ownerToken.value = ''; contract.value = null; phase.value = 'identify'
}

onMounted(async () => {
  try { config.value = (await api.get('/api/v1/timeshare/public/portal-config')).data } catch { /* fixed fallback copy below */ }
  if (ownerToken.value) await loadPortal()
})
</script>

<template>
  <main dir="rtl" class="min-h-dvh bg-gradient-to-br from-sky-950 via-blue-950 to-cyan-900 p-4 text-gray-900 sm:p-6">
    <div class="mx-auto w-full max-w-5xl">
      <header class="mb-6 flex flex-wrap items-center justify-between gap-3 text-white">
        <div><p class="text-xs font-black tracking-[0.2em] text-cyan-300">EL KHEIMA BEACH RESORT</p><h1 class="mt-1 text-2xl font-black">بوابة عملاء الملكية الجزئية</h1></div>
        <button v-if="phase === 'portal'" class="min-h-11 rounded-xl border border-white/30 px-4 text-sm font-bold" @click="logoutPortal">إنهاء الجلسة</button>
      </header>

      <section v-if="phase !== 'portal'" class="mx-auto max-w-md rounded-3xl bg-white p-6 shadow-2xl sm:p-8">
        <template v-if="phase === 'identify'">
          <h2 class="text-xl font-black">تابع عقدك بأمان</h2><p class="mt-2 text-sm leading-6 text-gray-600">اكتب رقم العقد ورقم الموبايل المسجل، وهنبعت كود تحقق على واتساب.</p>
          <form class="mt-6 space-y-4" @submit.prevent="requestOtp">
            <label class="block text-sm font-bold">رقم العقد<input v-model="contractNumber" required autocomplete="off" dir="ltr" class="mt-1 min-h-12 w-full rounded-xl border px-4"></label>
            <label class="block text-sm font-bold">رقم الموبايل المسجل<input v-model="phone" required inputmode="tel" autocomplete="tel" dir="ltr" class="mt-1 min-h-12 w-full rounded-xl border px-4"></label>
            <button :disabled="busy" class="min-h-12 w-full rounded-xl bg-cyan-700 font-bold text-white disabled:opacity-50">{{ busy ? 'جارٍ الإرسال...' : 'إرسال كود التحقق' }}</button>
          </form>
        </template>
        <template v-else>
          <h2 class="text-xl font-black">أدخل كود واتساب</h2><p class="mt-2 text-sm leading-6 text-gray-600">{{ message }}</p>
          <form class="mt-6 space-y-4" @submit.prevent="confirmOtp">
            <input v-model="otpCode" required inputmode="numeric" autocomplete="one-time-code" maxlength="8" dir="ltr" class="min-h-14 w-full rounded-xl border px-4 text-center text-2xl font-black tracking-[0.5em]">
            <button :disabled="busy" class="min-h-12 w-full rounded-xl bg-cyan-700 font-bold text-white disabled:opacity-50">{{ busy ? 'جارٍ التحقق...' : 'دخول آمن' }}</button>
            <button type="button" class="w-full text-sm text-cyan-800 underline" @click="phase = 'identify'">تعديل البيانات</button>
          </form>
        </template>
        <p v-if="error" role="alert" class="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{{ error }}</p>
      </section>

      <template v-else>
        <nav class="mb-5 grid grid-cols-2 gap-2 rounded-2xl bg-white/10 p-2 sm:grid-cols-4" aria-label="أقسام البوابة">
          <button v-for="item in [{id:'contract',label:'العقد'},{id:'payments',label:'المدفوعات'},{id:'visits',label:'الزيارات'},{id:'support',label:'خدمة العملاء'}]" :key="item.id"
            class="min-h-12 rounded-xl px-3 text-sm font-bold text-white" :class="activeSection === item.id ? 'bg-cyan-600' : 'bg-white/10'" @click="activeSection = item.id as typeof activeSection">{{ item.label }}</button>
        </nav>
        <p v-if="message" role="status" class="mb-4 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">{{ message }}</p>
        <p v-if="error" role="alert" class="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{{ error }}</p>

        <section v-if="activeSection === 'contract' && contract" class="rounded-3xl bg-white p-5 shadow-xl sm:p-7">
          <div class="flex flex-wrap items-start justify-between gap-3"><div><p class="text-sm text-gray-500">رقم العقد</p><h2 class="text-2xl font-black">{{ contract.contract_number }}</h2><p class="mt-1 text-gray-600">{{ contract.customer_name }}</p></div><button class="min-h-11 rounded-xl bg-cyan-700 px-4 font-bold text-white" @click="downloadContract">تحميل PDF</button></div>
          <dl class="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><div v-for="row in [['الوحدة',contract.unit_number || contract.room_type],['الأسبوع',contract.week_number || '—'],['الليالي سنويًا',contract.nights_per_year],['الموسم',contract.season],['الحالة',contract.status],['المدة',`${dateLabel(contract.start_date)} — ${dateLabel(contract.end_date)}`]]" :key="String(row[0])" class="rounded-xl bg-gray-50 p-4"><dt class="text-xs text-gray-500">{{ row[0] }}</dt><dd class="mt-1 font-bold">{{ row[1] }}</dd></div></dl>
        </section>

        <section v-else-if="activeSection === 'payments'" class="space-y-5">
          <div v-for="group in [{title:'الأقساط',rows:installments},{title:'رسوم الصيانة',rows:maintenanceDues}]" :key="group.title" class="rounded-3xl bg-white p-5 shadow-xl"><h2 class="text-lg font-black">{{ group.title }}</h2><div class="mt-4 space-y-2"><p v-if="!group.rows.length" class="text-sm text-gray-500">لا توجد بيانات.</p><div v-for="payment in group.rows" :key="payment.id" class="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-gray-50 p-3"><div><p class="font-bold">{{ money(payment.amount) }}</p><p class="text-xs text-gray-500">استحقاق {{ dateLabel(payment.due_date) }}</p></div><span class="rounded-full bg-blue-100 px-3 py-1 text-xs font-bold text-blue-800 dark:bg-blue-950/40 dark:text-blue-300">{{ payment.status }}</span></div></div></div>
        </section>

        <section v-else-if="activeSection === 'visits'" class="grid gap-5 lg:grid-cols-2">
          <form class="rounded-3xl bg-white p-5 shadow-xl space-y-4" @submit.prevent="submitVisit"><h2 class="text-lg font-black">طلب زيارة جديد</h2><label class="block text-sm font-bold">البداية المفضلة<input v-model="visitForm.preferred_start" type="date" required class="mt-1 min-h-11 w-full rounded-xl border px-3"></label><label class="block text-sm font-bold">النهاية المفضلة<input v-model="visitForm.preferred_end" type="date" :min="visitForm.preferred_start" required class="mt-1 min-h-11 w-full rounded-xl border px-3"></label><label class="block text-sm font-bold">ملاحظات<textarea v-model="visitForm.notes" class="mt-1 min-h-24 w-full rounded-xl border p-3"></textarea></label><label class="flex gap-2 text-sm leading-6"><input v-model="visitForm.accepted" type="checkbox" required class="mt-1">أوافق على شروط الزيارة وقواعد الحجز الحالية.</label><button :disabled="busy || !config" class="min-h-12 w-full rounded-xl bg-cyan-700 font-bold text-white disabled:opacity-50">إرسال الطلب</button></form>
          <div class="rounded-3xl bg-white p-5 shadow-xl"><h2 class="text-lg font-black">طلباتي</h2><div class="mt-4 space-y-2"><p v-if="!visits.length" class="text-sm text-gray-500">لا توجد طلبات.</p><div v-for="visit in visits" :key="visit.id" class="rounded-xl bg-gray-50 p-3"><div class="flex justify-between gap-2"><b>{{ dateLabel(visit.preferred_start) }} — {{ dateLabel(visit.preferred_end) }}</b><span class="text-xs font-bold">{{ visit.status }}</span></div><p v-if="visit.rejection_reason" class="mt-2 text-sm text-red-700 dark:text-red-300">{{ visit.rejection_reason }}</p></div></div></div>
        </section>

        <section v-else class="grid gap-5 lg:grid-cols-2">
          <form class="rounded-3xl bg-white p-5 shadow-xl space-y-4" @submit.prevent="submitTicket"><h2 class="text-lg font-black">تذكرة جديدة</h2><input v-model="ticketForm.subject" required minlength="3" placeholder="الموضوع" class="min-h-11 w-full rounded-xl border px-3"><textarea v-model="ticketForm.message" required minlength="3" placeholder="اكتب طلبك بالتفصيل" class="min-h-28 w-full rounded-xl border p-3"></textarea><button :disabled="busy" class="min-h-12 w-full rounded-xl bg-cyan-700 font-bold text-white">إرسال لخدمة العملاء</button></form>
          <div class="space-y-3"><p v-if="!tickets.length" class="rounded-3xl bg-white p-5 text-sm text-gray-500">لا توجد تذاكر.</p><article v-for="ticket in tickets" :key="ticket.id" class="rounded-3xl bg-white p-5 shadow-xl"><div class="flex justify-between gap-2"><h2 class="font-black">{{ ticket.subject }}</h2><span class="text-xs font-bold">{{ ticket.status }}</span></div><div class="mt-3 space-y-2"><div v-for="replyItem in ticket.replies" :key="replyItem.id" class="rounded-xl p-3 text-sm" :class="replyItem.author_type === 'owner' ? 'bg-cyan-50' : 'bg-gray-100'"><b>{{ replyItem.author_type === 'owner' ? 'أنت' : 'خدمة العملاء' }}</b><p class="mt-1 whitespace-pre-wrap">{{ replyItem.message }}</p></div></div><div class="mt-3 flex gap-2"><input v-model="replyText[ticket.id]" placeholder="اكتب ردًا" class="min-h-11 flex-1 rounded-xl border px-3"><button class="rounded-xl bg-cyan-700 px-4 font-bold text-white" @click="reply(ticket)">إرسال</button></div></article></div>
        </section>
      </template>
    </div>
  </main>
</template>

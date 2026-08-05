<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { usePrintDocument, useOfflineQueue } from '@resort-os/core/composables'
import { useToast } from '@resort-os/ui'

const toast = useToast()
const { t } = useI18n()
const { printBlob } = usePrintDocument()

// ── Offline queue ──────────────────────────────────────────────────────────────
// wagdy.md #13/#37: كان هنا queue محلي منفصل (localStorage، كود مكرر) —
// اتصلح باستخدام useOfflineQueue('beach') المشترك (IndexedDB، نفس نمط
// المطعم/الكافيه). فيه فرق حقيقي مهم اكتشفناه أثناء الدمج: الـ queue القديم
// كان بيعيد إرسال البيع وقت الـ retry من غير أي مفتاح idempotency — لو رد
// السيرفر ضاع بعد ما خصم السعة فعلاً، الـ retry كان يعمل بيع مزدوج حقيقي.
// الـ composable المشترك بيبعت local_id مع كل retry، وbeach.services.sell_ticket
// بقى يتجاهل أي retry بنفس الـ local_id ويرجّع نفس المعاملة القديمة.
const { isOnline, pendingCount, submitOrder: submitBeachSale } = useOfflineQueue('beach')

// مطابق فعليًا لـ app/modules/beach/schemas.py::BeachInventoryRead
interface BeachInventory {
  capacity_max: number
  capacity_used: number
  available_slots: number
  capacity_pct: number
  towels_total: number
  towels_available: number
  towels_used: number
  adult_price: number
  child_price: number
  resident_price: number
  towel_price: number
  surge_active: boolean
  surge_multiplier: number
}

// ── POS-03: العملات المدعومة للكاش الأجنبي (نفس نمط POSPaymentModal) ──────────
const FOREIGN_CURRENCIES = ['USD', 'EUR'] as const
type CashCurrency = 'EGP' | typeof FOREIGN_CURRENCIES[number]
interface FxRate { from_currency: string; to_currency: string; rate: string }

const auth = useAuthStore()
const branchId = computed(() => auth.branchId)
const inventory = ref<BeachInventory | null>(null)
const loading = ref(false)
const submitting = ref(false)
const successMsg = ref('')
const errorMsg = ref('')

// بعد أي تزامن ناجح (كامل أو جزئي)، سعة/إشغال الشاطئ المعروضة لازم تتحدّث
// فورًا (مش تستنى الـ poll الدوري كل 30 ثانية).
watch(pendingCount, (curr, prev) => {
  if (curr < prev) fetchInventory()
})

// Cart state
const adultQty    = ref(0)
const childQty    = ref(0)
const residentQty = ref(0)
const towelQty    = ref(0)

// ── POS-03: حالة العملة ────────────────────────────────────────────────────────
const cashCurrency   = ref<CashCurrency>('EGP')
const fxRates        = ref<Record<string, number>>({})
const fxLoading      = ref(false)
// المبلغ الذي استلمه الكاشير فعليًا بالعملة الأجنبية (حقل الإدخال)
const foreignReceived = ref('')

const currentFxRate = computed(() =>
  cashCurrency.value === 'EGP' ? 1 : (fxRates.value[cashCurrency.value] ?? 0),
)

/** المبلغ المطلوب بالعملة الأجنبية = total_EGP / fx_rate */
const totalInForeign = computed(() => {
  if (cashCurrency.value === 'EGP' || currentFxRate.value <= 0) return null
  return +(total.value / currentFxRate.value).toFixed(2)
})

/** الفكة دايمًا بالجنيه (قرار Mohamed 2026-08-05):
 *  لو الكاشير استلم USD/EUR، الفكة = (received × fx_rate − total) جنيه */
const changeInEGP = computed(() => {
  if (cashCurrency.value === 'EGP') return null   // مش مستخدم في EGP mode
  if (currentFxRate.value <= 0) return null
  const received = parseFloat(foreignReceived.value)
  if (isNaN(received) || totalInForeign.value === null) return null
  return +((received - totalInForeign.value) * currentFxRate.value).toFixed(2)
})

async function fetchFxRates() {
  if (fxLoading.value) return
  fxLoading.value = true
  try {
    const { data } = await api.get(
      ENDPOINTS.finance?.exchangeRates ?? '/finance/exchange-rates',
      { params: { to_currency: 'EGP' } },
    )
    const rates: Record<string, number> = {}
    const items: FxRate[] = data?.items ?? data ?? []
    for (const r of items) {
      if (r.to_currency === 'EGP') rates[r.from_currency] = parseFloat(r.rate)
    }
    fxRates.value = rates
  } catch {
    // لو فشل نفضل EGP فقط بدون إظهار خطأ
  } finally {
    fxLoading.value = false
  }
}

// UI-only — payment_method مش بيتبعت للسيرفر في عملية البيع العادية
const paymentMethod = ref<'cash' | 'card' | 'wallet'>('cash')

// Ref for auto-focus after sale
const firstButtonRef = ref<HTMLButtonElement | null>(null)

const prices = computed(() => {
  if (!inventory.value) return { adult: 0, child: 0, resident: 0, towel: 0 }
  const m = inventory.value.surge_active ? inventory.value.surge_multiplier : 1
  return {
    adult:    Math.round(inventory.value.adult_price * m),
    child:    Math.round(inventory.value.child_price * m),
    resident: Math.round(inventory.value.resident_price * m),
    towel:    inventory.value.towel_price, // towels no surge
  }
})

const total = computed(() =>
  adultQty.value * prices.value.adult +
  childQty.value * prices.value.child +
  residentQty.value * prices.value.resident +
  towelQty.value * prices.value.towel,
)

const hasItems = computed(() => total.value > 0)

const availableSlots = computed(() => inventory.value?.available_slots ?? 0)
const occupancyPct   = computed(() => inventory.value?.capacity_pct ?? 0)

function adjust(type: 'adult' | 'child' | 'resident' | 'towel', delta: number) {
  if (type === 'adult')    adultQty.value    = Math.max(0, adultQty.value + delta)
  if (type === 'child')    childQty.value    = Math.max(0, childQty.value + delta)
  if (type === 'resident') residentQty.value = Math.max(0, residentQty.value + delta)
  if (type === 'towel')    towelQty.value    = Math.max(0, towelQty.value + delta)
}

function clearCart() {
  adultQty.value    = 0
  childQty.value    = 0
  residentQty.value = 0
  towelQty.value    = 0
  foreignReceived.value = ''
}

async function fetchInventory() {
  loading.value = true
  try {
    // ⚠️ باج حقيقي كان هنا: `/api/v1/beach/inventory/${branchId}` (branch_id
    // كجزء من الـ path) — الـ route الحقيقي (app/modules/beach/api/router.py)
    // بياخد branch_id كـ query param، مش path segment، فالطلب كان بيرجع 404
    // بصمت (console.error بس، من غير toast) في كل مرة الكاشير يفتح شاشة
    // الشاطئ — يعني سعة/إشغال الشاطئ ما كانتش بتظهر أبداً.
    const { data } = await api.get(ENDPOINTS.beach.inventory, { params: { branch_id: branchId.value } })
    inventory.value = data
  } catch (e) {
    toast.error(t('backoffice.beachPos.loadInventoryError'))
  } finally {
    loading.value = false
  }
}

interface BeachSaleLineItem { tx_type: string; quantity: number; cartKey: 'adult' | 'child' | 'resident' | 'towel' }

// ⚠️ باج حقيقي كان هنا: كان الكود بيبني طلب واحد مجمّع (entries[] + towels +
// towel_price + payment_method) ويبعته لـ /beach/sell — الـ schema الحقيقي
// (app/modules/beach/schemas.py::BeachSellRequest) بياخد صنف واحد بس لكل
// طلب (`tx_type` + `quantity`)، مفيش batching ولا payment_method خالص، وده
// كان بيرجّع 422 "tx_type: Field required" في كل مرة أي كاشير يحاول يكمّل
// بيع فيه أكتر من صنف — يعني شاشة الشاطئ كانت 100% معطّلة (زرار "إتمام
// البيع" مايشتغلش أبداً). اتصلح ببناء طلب منفصل لكل صنف موجود في السلة.
function buildCartLineItems(): BeachSaleLineItem[] {
  const items: BeachSaleLineItem[] = []
  if (adultQty.value > 0)    items.push({ tx_type: 'entry',          quantity: adultQty.value,    cartKey: 'adult' })
  if (childQty.value > 0)    items.push({ tx_type: 'entry_child',    quantity: childQty.value,    cartKey: 'child' })
  if (residentQty.value > 0) items.push({ tx_type: 'entry_resident', quantity: residentQty.value, cartKey: 'resident' })
  if (towelQty.value > 0)    items.push({ tx_type: 'towel_rent',     quantity: towelQty.value,    cartKey: 'towel' })
  return items
}

async function printTicket(txId: number) {
  try {
    const ticketRes = await api.get(ENDPOINTS.beach.ticket(txId), { responseType: 'blob' })
    const outcome = printBlob(ticketRes.data, `ticket-${txId}.pdf`)
    if (outcome.downloadedInstead) {
      toast.error(t('backoffice.beachPos.ticketDownloadedInstead'))
    }
  } catch {
    // ticket printing is optional — don't block success
  }
}

async function completeSale() {
  if (!hasItems.value || submitting.value) return

  // POS-03: تحقق من سعر الصرف قبل الإرسال لو الكاشير اختار عملة أجنبية
  if (cashCurrency.value !== 'EGP') {
    if (currentFxRate.value <= 0) {
      errorMsg.value = t('backoffice.beachPos.noFxRate', { currency: cashCurrency.value })
      setTimeout(() => { errorMsg.value = '' }, 4000)
      return
    }
    const received = parseFloat(foreignReceived.value)
    if (totalInForeign.value !== null && (isNaN(received) || received < totalInForeign.value)) {
      errorMsg.value = t('backoffice.beachPos.foreignInsufficient')
      setTimeout(() => { errorMsg.value = '' }, 4000)
      return
    }
  }

  submitting.value = true
  try {
    const lineItems = buildCartLineItems()
    const soldTxIds: number[] = []
    let anyQueued = false

    // POS-03: payload إضافي للعملة — يُضاف لكل صنف في السلة
    const fxPayload = cashCurrency.value !== 'EGP' && currentFxRate.value > 0
      ? { payment_currency: cashCurrency.value, payment_fx_rate: currentFxRate.value }
      : {}

    for (const item of lineItems) {
      // submitOrder بيرجّع null لو اتقفل في الطابور (offline أو انقطاع نت
      // لحظي)، ويرمي الخطأ نفسه لو السيرفر رفضه صراحة (زي تجاوز السعة) —
      // نوقف هنا في الحالة دي، الأصناف اللي اتباعت قبل كده فعلاً اتسجّلت
      // (مش rollback جماعي، كل عملية مستقلة).
      const data = await submitBeachSale(branchId.value ?? 0, {
        tx_type: item.tx_type,
        quantity: item.quantity,
        ...fxPayload,
      })
      if (data === null) { anyQueued = true; continue }
      soldTxIds.push(data.id)
    }

    for (const txId of soldTxIds) await printTicket(txId)

    clearCart()
    if (soldTxIds.length || anyQueued) await fetchInventory()

    successMsg.value = anyQueued
      ? t('backoffice.beachPos.partialSaleQueued')
      : t('backoffice.beachPos.saleSuccess')
    setTimeout(() => { successMsg.value = '' }, 4000)

    // Auto-focus back to first price button
    await nextTick()
    firstButtonRef.value?.focus()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? t('backoffice.beachPos.saleError')
    setTimeout(() => { errorMsg.value = '' }, 4000)
  } finally {
    submitting.value = false
  }
}

// useOfflineQueue('beach') بيتكفّل بـ online/offline listeners والـ
// sync التلقائي (وقت reconnect + safety poll داخلي) لوحده — مش محتاجين
// نلمسه هنا خالص، بس الـ watch(pendingCount) فوق بيحدّث السعة بعد أي
// تزامن منه.
let refreshInterval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchInventory()
  fetchFxRates()  // POS-03: جلب أسعار الصرف عند فتح الشاشة
  refreshInterval = setInterval(fetchInventory, 30_000)
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})
</script>

<template>
  <div class="p-4 h-full">
    <!-- ── Offline banner — visible الطول، مش toast بيختفي ── -->
    <div
      v-if="!isOnline"
      class="bg-amber-500 text-white text-xs font-bold px-4 py-1.5 rounded-lg mb-3 flex items-center justify-center gap-2"
    >
      <span>⚠️ {{ t('backoffice.beachPos.offlineBanner') }}</span>
      <span v-if="pendingCount > 0" class="bg-amber-700 px-2 py-0.5 rounded-full">{{ t('backoffice.beachPos.pendingCount', { count: pendingCount }) }}</span>
    </div>
    <div
      v-else-if="pendingCount > 0"
      class="bg-blue-500 text-white text-xs font-bold px-4 py-1.5 rounded-lg mb-3 flex items-center justify-center gap-2"
    >
      <span>⏳ {{ t('backoffice.beachPos.syncingBanner', { count: pendingCount }) }}</span>
    </div>

    <!-- Loading splash -->
    <div v-if="loading && !inventory" class="flex items-center justify-center h-64">
      <div class="motion-safe:animate-spin w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <!-- No connection -->
    <div v-else-if="!inventory && !loading" class="flex flex-col items-center justify-center h-64 text-gray-500 gap-3">
      <div class="text-5xl">⚠️</div>
      <p class="font-medium">{{ t('backoffice.beachPos.cannotConnect') }}</p>
      <button @click="fetchInventory" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
        {{ t('backoffice.beachPos.retry') }}
      </button>
    </div>

    <!-- Main content -->
    <div v-else-if="inventory" class="grid grid-cols-1 lg:grid-cols-2 gap-4 h-full">

      <!-- ═══ LEFT: Status + Price Cards ═══ -->
      <div class="space-y-4 overflow-y-auto">

        <!-- Beach status card -->
        <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border p-4 shadow-sm">
          <div class="flex items-center justify-between mb-3">
            <h2 class="font-bold text-gray-900 dark:text-gray-100 text-base">{{ t('backoffice.beachPos.beachStatus') }}</h2>
            <div class="flex items-center gap-2">
              <span
                v-if="inventory.surge_active"
                class="animate-pulse rounded-full bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-700 dark:bg-amber-950/50 dark:text-amber-300"
              >🌊 SURGE ×{{ inventory.surge_multiplier }}</span>
              <button
                @click="fetchInventory"
                :class="['text-gray-400 transition-colors hover:text-blue-600 dark:hover:text-blue-300', loading ? 'motion-safe:animate-spin' : '']"
                :title="t('backoffice.beachPos.refresh')"
              >↻</button>
            </div>
          </div>

          <!-- Occupancy bar -->
          <div class="mb-3">
            <div class="mb-1 flex justify-between text-sm text-gray-600 dark:text-gray-300">
              <span>{{ t('backoffice.beachPos.occupancy') }}</span>
              <span class="font-medium">
                {{ inventory.capacity_used }} / {{ inventory.capacity_max }}
                <span class="text-xs text-gray-400">({{ occupancyPct }}%)</span>
              </span>
            </div>
            <div class="h-3 w-full rounded-full bg-gray-200 dark:bg-gray-700">
              <div
                class="h-3 rounded-full transition-all duration-500"
                :class="occupancyPct >= 90 ? 'bg-red-500' : occupancyPct >= 70 ? 'bg-amber-500' : 'bg-green-500'"
                :style="{ width: Math.min(occupancyPct, 100) + '%' }"
              />
            </div>
          </div>

          <!-- Available slots — سعة الشاطئ مجمّعة (مفيش حصة منفصلة بالغ/طفل) -->
          <div class="grid grid-cols-2 gap-2">
            <div class="rounded-lg bg-blue-50 p-2.5 text-center dark:bg-blue-950/40">
              <div class="text-2xl font-black text-blue-700 dark:text-blue-300">{{ availableSlots }}</div>
              <div class="mt-0.5 text-xs text-blue-600 dark:text-blue-400">{{ t('backoffice.beachPos.availableSlots') }}</div>
            </div>
            <div class="rounded-lg bg-amber-50 p-2.5 text-center dark:bg-amber-950/40">
              <div class="text-2xl font-black text-amber-700 dark:text-amber-300">{{ inventory.towels_available }}</div>
              <div class="mt-0.5 text-xs text-amber-600 dark:text-amber-400">{{ t('backoffice.beachPos.towelsAvailable') }}</div>
            </div>
          </div>
        </div>

        <!-- Price cards grid -->
        <div class="grid grid-cols-2 gap-3">

          <!-- Adult -->
          <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border p-4 shadow-sm">
            <div class="text-center mb-3">
              <div class="text-3xl mb-1">👤</div>
              <div class="font-bold text-gray-900 dark:text-gray-100 text-sm">{{ t('backoffice.beachPos.adult') }}</div>
              <div class="mt-1 text-2xl font-black text-blue-700 dark:text-blue-300">
                {{ prices.adult }}<span class="text-xs font-normal text-gray-500 ms-1">{{ t('backoffice.beachPos.egp') }}</span>
              </div>
              <div v-if="inventory.surge_active" class="mt-0.5 text-xs text-amber-600 dark:text-amber-300">
                {{ t('backoffice.beachPos.originalPrice', { price: inventory.adult_price }) }}
              </div>
            </div>
            <div class="flex items-center justify-center gap-3">
              <button
                @click="adjust('adult', -1)"
                :disabled="adultQty === 0"
                class="h-9 w-9 rounded-lg bg-gray-100 text-lg font-bold leading-none transition-colors hover:bg-gray-200 disabled:opacity-40 dark:bg-gray-800 dark:hover:bg-gray-700"
              >−</button>
              <span class="text-xl font-black w-8 text-center text-gray-900 dark:text-gray-100">{{ adultQty }}</span>
              <button
                ref="firstButtonRef"
                @click="adjust('adult', 1)"
                class="w-9 h-9 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-bold text-lg transition-colors leading-none"
              >+</button>
            </div>
          </div>

          <!-- Child -->
          <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border p-4 shadow-sm">
            <div class="text-center mb-3">
              <div class="text-3xl mb-1">🧒</div>
              <div class="font-bold text-gray-900 dark:text-gray-100 text-sm">{{ t('backoffice.beachPos.child') }}</div>
              <div class="mt-1 text-2xl font-black text-green-700 dark:text-green-300">
                {{ prices.child }}<span class="text-xs font-normal text-gray-500 ms-1">{{ t('backoffice.beachPos.egp') }}</span>
              </div>
              <div v-if="inventory.surge_active" class="mt-0.5 text-xs text-amber-600 dark:text-amber-300">
                {{ t('backoffice.beachPos.originalPrice', { price: inventory.child_price }) }}
              </div>
            </div>
            <div class="flex items-center justify-center gap-3">
              <button
                @click="adjust('child', -1)"
                :disabled="childQty === 0"
                class="h-9 w-9 rounded-lg bg-gray-100 text-lg font-bold leading-none transition-colors hover:bg-gray-200 disabled:opacity-40 dark:bg-gray-800 dark:hover:bg-gray-700"
              >−</button>
              <span class="text-xl font-black w-8 text-center text-gray-900 dark:text-gray-100">{{ childQty }}</span>
              <button
                @click="adjust('child', 1)"
                class="w-9 h-9 rounded-lg bg-green-600 hover:bg-green-700 text-white font-bold text-lg transition-colors leading-none"
              >+</button>
            </div>
          </div>

          <!-- Resident -->
          <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border p-4 shadow-sm">
            <div class="text-center mb-3">
              <div class="text-3xl mb-1">🏠</div>
              <div class="font-bold text-gray-900 dark:text-gray-100 text-sm">{{ t('backoffice.beachPos.resident') }}</div>
              <div class="mt-1 text-2xl font-black text-purple-700 dark:text-purple-300">
                {{ prices.resident }}<span class="text-xs font-normal text-gray-500 ms-1">{{ t('backoffice.beachPos.egp') }}</span>
              </div>
              <div v-if="inventory.surge_active" class="mt-0.5 text-xs text-amber-600 dark:text-amber-300">
                {{ t('backoffice.beachPos.originalPrice', { price: inventory.resident_price }) }}
              </div>
            </div>
            <div class="flex items-center justify-center gap-3">
              <button
                @click="adjust('resident', -1)"
                :disabled="residentQty === 0"
                class="h-9 w-9 rounded-lg bg-gray-100 text-lg font-bold leading-none transition-colors hover:bg-gray-200 disabled:opacity-40 dark:bg-gray-800 dark:hover:bg-gray-700"
              >−</button>
              <span class="text-xl font-black w-8 text-center text-gray-900 dark:text-gray-100">{{ residentQty }}</span>
              <button
                @click="adjust('resident', 1)"
                class="w-9 h-9 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-bold text-lg transition-colors leading-none"
              >+</button>
            </div>
          </div>

          <!-- Towel -->
          <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border p-4 shadow-sm">
            <div class="text-center mb-3">
              <div class="text-3xl mb-1">🏊</div>
              <div class="font-bold text-gray-900 dark:text-gray-100 text-sm">{{ t('backoffice.beachPos.towel') }}</div>
              <div class="mt-1 text-2xl font-black text-amber-700 dark:text-amber-300">
                {{ prices.towel }}<span class="text-xs font-normal text-gray-500 ms-1">{{ t('backoffice.beachPos.egp') }}</span>
              </div>
              <div class="text-xs text-gray-400 mt-0.5">{{ t('backoffice.beachPos.noSurge') }}</div>
            </div>
            <div class="flex items-center justify-center gap-3">
              <button
                @click="adjust('towel', -1)"
                :disabled="towelQty === 0"
                class="h-9 w-9 rounded-lg bg-gray-100 text-lg font-bold leading-none transition-colors hover:bg-gray-200 disabled:opacity-40 dark:bg-gray-800 dark:hover:bg-gray-700"
              >−</button>
              <span class="text-xl font-black w-8 text-center text-gray-900 dark:text-gray-100">{{ towelQty }}</span>
              <button
                @click="adjust('towel', 1)"
                class="w-9 h-9 rounded-lg bg-amber-500 hover:bg-amber-600 text-white font-bold text-lg transition-colors leading-none"
              >+</button>
            </div>
          </div>

        </div>
      </div>

      <!-- ═══ RIGHT: Order Summary ═══ -->
      <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border shadow-sm flex flex-col min-h-[480px]">

        <!-- Header -->
        <div class="p-4 border-b border-stone-100">
          <h2 class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.beachPos.orderSummary') }}</h2>
        </div>

        <!-- Cart items list -->
        <div class="flex-1 p-4 space-y-2 overflow-y-auto">
          <div
            v-if="adultQty > 0"
            class="flex items-center justify-between py-2.5 border-b border-dashed border-stone-200 dark:border-border"
          >
            <span class="text-gray-700 dark:text-gray-300">👤 {{ t('backoffice.beachPos.cartLine', { label: t('backoffice.beachPos.adult'), qty: adultQty }) }}</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">{{ t('backoffice.beachPos.lineTotal', { amount: adultQty * prices.adult }) }}</span>
          </div>
          <div
            v-if="childQty > 0"
            class="flex items-center justify-between py-2.5 border-b border-dashed border-stone-200 dark:border-border"
          >
            <span class="text-gray-700 dark:text-gray-300">🧒 {{ t('backoffice.beachPos.cartLine', { label: t('backoffice.beachPos.child'), qty: childQty }) }}</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">{{ t('backoffice.beachPos.lineTotal', { amount: childQty * prices.child }) }}</span>
          </div>
          <div
            v-if="residentQty > 0"
            class="flex items-center justify-between py-2.5 border-b border-dashed border-stone-200 dark:border-border"
          >
            <span class="text-gray-700 dark:text-gray-300">🏠 {{ t('backoffice.beachPos.cartLine', { label: t('backoffice.beachPos.resident'), qty: residentQty }) }}</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">{{ t('backoffice.beachPos.lineTotal', { amount: residentQty * prices.resident }) }}</span>
          </div>
          <div
            v-if="towelQty > 0"
            class="flex items-center justify-between py-2.5 border-b border-dashed border-stone-200 dark:border-border"
          >
            <span class="text-gray-700 dark:text-gray-300">🏊 {{ t('backoffice.beachPos.cartLine', { label: t('backoffice.beachPos.towel'), qty: towelQty }) }}</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">{{ t('backoffice.beachPos.lineTotal', { amount: towelQty * prices.towel }) }}</span>
          </div>

          <!-- Empty state -->
          <div v-if="!hasItems" class="flex flex-col items-center justify-center py-12 text-gray-400">
            <div class="text-5xl mb-3">🏖️</div>
            <p class="text-sm">{{ t('backoffice.beachPos.noItemsSelected') }}</p>
            <p class="text-xs mt-1">{{ t('backoffice.beachPos.tapToAdd') }}</p>
          </div>
        </div>

        <!-- Footer: total + payment + buttons -->
        <div class="p-4 border-t border-stone-200 dark:border-border space-y-3">

          <!-- Total -->
          <div class="flex items-center justify-between">
            <span class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.beachPos.total') }}</span>
            <span class="text-2xl font-black text-blue-700 dark:text-blue-300">{{ total }} <span class="text-sm font-normal">{{ t('backoffice.beachPos.egp') }}</span></span>
          </div>

          <!-- Payment method selector -->
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="m in [
                { val: 'cash',   label: t('backoffice.beachPos.payCash'),   icon: '💵' },
                { val: 'card',   label: t('backoffice.beachPos.payCard'),  icon: '💳' },
                { val: 'wallet', label: t('backoffice.beachPos.payWallet'), icon: '📱' },
              ]"
              :key="m.val"
              @click="paymentMethod = (m.val as 'cash' | 'card' | 'wallet'); cashCurrency = 'EGP'; foreignReceived = ''"
              :class="[
                'py-2 rounded-lg text-sm font-medium transition-all border-2',
                paymentMethod === m.val
                  ? 'border-blue-600 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-950/40 dark:text-blue-300'
                  : 'border-stone-200 text-gray-600 hover:border-blue-300 hover:bg-gray-50 dark:border-border dark:text-gray-400 dark:hover:bg-gray-800',
              ]"
            >{{ m.icon }} {{ m.label }}</button>
          </div>

          <!-- POS-03: اختيار عملة الكاش (يظهر بس لو طريقة الدفع كاش) ──────── -->
          <div v-if="paymentMethod === 'cash'" class="rounded-xl border border-stone-200 dark:border-border p-3 space-y-3">
            <!-- أزرار اختيار العملة -->
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.beachPos.cashCurrency') }}:</span>
              <button
                v-for="cur in (['EGP', ...FOREIGN_CURRENCIES] as CashCurrency[])"
                :key="cur"
                type="button"
                :aria-pressed="cashCurrency === cur"
                :class="[
                  'px-3 py-1 rounded-lg border-2 text-xs font-bold transition-colors',
                  cashCurrency === cur
                    ? 'border-blue-600 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-950/40 dark:text-blue-300'
                    : 'border-stone-200 text-gray-600 hover:border-blue-300 dark:border-border dark:text-gray-400',
                ]"
                @click="cashCurrency = cur; foreignReceived = ''"
              >
                {{ cur === 'EGP' ? '🇪🇬 EGP' : cur === 'USD' ? '🇺🇸 USD' : '🇪🇺 EUR' }}
              </button>
              <span v-if="fxLoading" class="text-xs text-gray-400">...</span>
              <span v-else-if="cashCurrency !== 'EGP' && currentFxRate > 0" class="text-xs text-gray-500 dark:text-gray-400">
                1 {{ cashCurrency }} = {{ currentFxRate }} ج
              </span>
              <span v-else-if="cashCurrency !== 'EGP'" class="text-xs text-red-500">
                {{ t('backoffice.beachPos.noFxRate', { currency: cashCurrency }) }}
              </span>
            </div>

            <!-- حقل الاستلام بالعملة الأجنبية (يظهر بس لو مش EGP) -->
            <template v-if="cashCurrency !== 'EGP' && currentFxRate > 0">
              <div class="rounded-lg bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 px-3 py-2 text-xs space-y-0.5">
                <div class="font-bold">{{ t('backoffice.beachPos.foreignCashHint') }}</div>
                <div class="tabular-nums">
                  {{ t('backoffice.beachPos.requiredInForeign', {
                    amount: totalInForeign?.toFixed(2) ?? '—',
                    currency: cashCurrency,
                    rate: currentFxRate,
                  }) }}
                </div>
              </div>
              <div>
                <label class="block text-xs font-semibold text-gray-600 dark:text-gray-300 mb-1">
                  {{ t('backoffice.beachPos.foreignReceivedLabel', { currency: cashCurrency }) }}
                </label>
                <input
                  v-model="foreignReceived"
                  type="number"
                  step="0.01"
                  min="0"
                  inputmode="decimal"
                  class="w-full rounded-lg border-2 border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-base font-bold tabular-nums focus:outline-none focus:border-blue-500"
                  :placeholder="totalInForeign?.toFixed(2) ?? '0.00'"
                />
              </div>
              <!-- الفكة بالجنيه دايمًا (قرار Mohamed 2026-08-05) -->
              <div
                v-if="changeInEGP !== null"
                :class="[
                  'rounded-lg px-3 py-2 flex items-center justify-between text-sm font-bold',
                  changeInEGP >= 0 ? 'bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-300' : 'bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300',
                ]"
              >
                <span>{{ t('backoffice.beachPos.changeInEGP') }}</span>
                <span class="tabular-nums">{{ changeInEGP >= 0 ? `${changeInEGP.toFixed(2)} ج` : '—' }}</span>
              </div>
            </template>
          </div>

          <!-- Feedback messages -->
          <transition name="fade">
            <div
              v-if="successMsg"
              class="rounded-lg bg-green-100 px-3 py-2 text-center text-sm font-medium text-green-700 dark:bg-green-950/50 dark:text-green-300"
            >{{ successMsg }}</div>
          </transition>
          <transition name="fade">
            <div
              v-if="errorMsg"
              class="rounded-lg bg-red-100 px-3 py-2 text-center text-sm font-medium text-red-700 dark:bg-red-950/50 dark:text-red-300"
            >{{ errorMsg }}</div>
          </transition>

          <!-- Action buttons -->
          <div class="grid grid-cols-2 gap-2">
            <button
              @click="clearCart"
              :disabled="!hasItems"
              class="rounded-xl border-2 border-stone-200 py-3 font-semibold text-gray-600 transition-colors hover:bg-gray-50 dark:bg-surface-2 disabled:opacity-40 dark:border-border dark:text-gray-300 dark:hover:bg-gray-800"
            >{{ t('backoffice.beachPos.clearOrder') }}</button>
            <button
              @click="completeSale"
              :disabled="!hasItems || submitting"
              class="py-3 rounded-xl bg-blue-700 text-white font-bold hover:bg-blue-800 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
            >
              <div
                v-if="submitting"
                class="motion-safe:animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"
              />
              <span>{{ submitting ? t('backoffice.beachPos.processing') : t('backoffice.beachPos.completeSale') }}</span>
            </button>
          </div>

        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

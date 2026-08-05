<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import {
  AppBadge,
  AppButton,
  AppModal,
  AppSelect,
  EmptyState,
  LoadingState,
  MoneyInput,
  SearchInput,
} from '@resort-os/ui'
import type { SelectOption } from '@resort-os/ui'
import type {
  CheckedInRoom,
  DiningOrderDetail,
  PaymentMethod,
} from './types'
import {
  cashPresetMinorValues,
  minorToMoney,
  moneyToMinor,
  remainingMinor,
} from './money'

// ── POS-03: العملات المدعومة للكاش الأجنبي ────────────────────────────
const FOREIGN_CURRENCIES = ['USD', 'EUR'] as const
type CashCurrency = 'EGP' | typeof FOREIGN_CURRENCIES[number]

interface FxRate { from_currency: string; to_currency: string; rate: string }

interface SplitRow {
  key: number
  paymentMethod: PaymentMethod
  amount: string
  roomId: string
  cashCurrency: CashCurrency
}

interface PMSRoom {
  id: number
  name: string
}

interface BookingRoom {
  room_id: number
}

interface CheckedInBooking {
  booking_number: string
  guest_name: string
  check_out: string
  rooms?: BookingRoom[]
}

const props = defineProps<{
  open: boolean
  order: DiningOrderDetail | null
  branchId: number | null
}>()
const emit = defineEmits<{
  close: []
  paid: [order: DiningOrderDetail]
}>()

const { t } = useI18n()
const { formatMoney } = useStaffFormat()
const currency = 'EGP'

const mode = ref<'single' | 'split'>('single')
const paymentMethod = ref<PaymentMethod>('cash')
const cashReceived = ref('')
const selectedRoomId = ref('')
const roomSearch = ref('')
const checkedInRooms = ref<CheckedInRoom[]>([])
const roomsLoading = ref(false)
const roomsLoaded = ref(false)
const roomsError = ref('')
const busy = ref(false)
const paymentError = ref('')
const pendingKey = ref('')
const pendingIntent = ref('')
let nextSplitKey = 3
const splitRows = ref<SplitRow[]>([])

// ── POS-03: أسعار الصرف وحالة العملة ──────────────────────────────────
const cashCurrency = ref<CashCurrency>('EGP')
const fxRates = ref<Record<string, number>>({})
const fxLoading = ref(false)

const currentFxRate = computed(() =>
  cashCurrency.value === 'EGP' ? 1 : (fxRates.value[cashCurrency.value] ?? 0),
)

/** المبلغ المطلوب بالعملة الأجنبية = total_EGP / fx_rate */
const totalInForeignCurrency = computed(() => {
  if (cashCurrency.value === 'EGP' || currentFxRate.value <= 0) return null
  return +(Number(props.order!.total) / currentFxRate.value).toFixed(2)
})

/** المبلغ الاستلامي بالعملة الأجنبية (ما يكتبه الكاشير) */
const foreignReceived = ref('')

/** الفكة بالعملة الأجنبية */
const foreignChangeMinor = computed(() => {
  if (cashCurrency.value === 'EGP' || currentFxRate.value <= 0) return null
  const received = parseFloat(foreignReceived.value)
  if (isNaN(received) || totalInForeignCurrency.value === null) return null
  return +(received - totalInForeignCurrency.value).toFixed(2)
})

const currencyOptions = computed<SelectOption[]>(() => [
  { value: 'EGP', label: `🇪🇬 ${t('backoffice.pos.payment.currencies.EGP')}` },
  ...FOREIGN_CURRENCIES.map(cur => ({
    value: cur,
    label: `${cur === 'USD' ? '🇺🇸' : '🇪🇺'} ${t(`backoffice.pos.payment.currencies.${cur}`, cur)}`,
  })),
])

async function fetchFxRates() {
  if (fxLoading.value) return
  fxLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance?.exchangeRates ?? '/finance/exchange-rates', {
      params: { to_currency: 'EGP' },
    })
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

const methodOptions = computed<Array<{ value: PaymentMethod; label: string; icon: string }>>(() => [
  { value: 'cash', label: t('backoffice.pos.payment.methods.cash'), icon: '💵' },
  { value: 'card', label: t('backoffice.pos.payment.methods.card'), icon: '💳' },
  { value: 'room', label: t('backoffice.pos.payment.methods.room'), icon: '🛏️' },
  { value: 'wallet', label: t('backoffice.pos.payment.methods.wallet'), icon: '👛' },
])

const totalMinor = computed(() => moneyToMinor(props.order?.total ?? null) ?? 0)
const receivedMinor = computed(() => moneyToMinor(cashReceived.value))
const cashChangeMinor = computed(() => {
  if (receivedMinor.value === null) return null
  return receivedMinor.value - totalMinor.value
})
const cashPresets = computed(() => cashPresetMinorValues(props.order?.total ?? 0))
const splitRemainingMinor = computed(() => remainingMinor(
  props.order?.total ?? 0,
  splitRows.value.map(row => row.amount),
) ?? totalMinor.value)

const filteredRooms = computed(() => {
  const query = roomSearch.value.trim().toLowerCase()
  if (!query) return checkedInRooms.value
  return checkedInRooms.value.filter(room =>
    room.name.toLowerCase().includes(query) ||
    room.guestName.toLowerCase().includes(query) ||
    room.bookingNumber.toLowerCase().includes(query),
  )
})

const roomOptions = computed<SelectOption[]>(() => checkedInRooms.value.map(room => ({
  value: room.id,
  label: `${room.name} — ${room.guestName}`,
})))

function initialSplitRows(): SplitRow[] {
  return [
    { key: 1, paymentMethod: 'cash', amount: '', roomId: '', cashCurrency: 'EGP' },
    { key: 2, paymentMethod: 'card', amount: '', roomId: '', cashCurrency: 'EGP' },
  ]
}

function resetPaymentState() {
  mode.value = 'single'
  paymentMethod.value = 'cash'
  cashCurrency.value = 'EGP'
  foreignReceived.value = ''
  cashReceived.value = props.order ? String(props.order.total) : ''
  selectedRoomId.value = ''
  roomSearch.value = ''
  paymentError.value = ''
  pendingKey.value = ''
  pendingIntent.value = ''
  splitRows.value = initialSplitRows()
}

watch(
  () => [props.open, props.order?.id] as const,
  ([open]) => {
    if (!open) return
    resetPaymentState()
    if (!roomsLoaded.value) loadCheckedInRooms()
    // POS-03: جلب أسعار الصرف عند فتح المودال
    fetchFxRates()
  },
  { immediate: true },
)

watch(
  () => props.branchId,
  () => {
    roomsLoaded.value = false
    checkedInRooms.value = []
    selectedRoomId.value = ''
    if (props.open) loadCheckedInRooms()
  },
)

function newIdempotencyKey(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `dining-pay-${Date.now()}-${Math.random().toString(36).slice(2)}`
  }
}

function ensureIdempotencyKey(intent: string): string {
  if (!pendingKey.value || pendingIntent.value !== intent) {
    pendingKey.value = newIdempotencyKey()
    pendingIntent.value = intent
  }
  return pendingKey.value
}

function resetIdempotencyForFinalRejection(error: any) {
  const code = error?.response?.data?.detail?.error_code
  if (code && code !== 'ORDER_PAYMENT_IN_PROGRESS') {
    pendingKey.value = ''
    pendingIntent.value = ''
  }
}

function paymentErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail
  const code = typeof detail === 'object' ? detail?.error_code : null
  const known: Record<string, string> = {
    NO_OPEN_SHIFT: 'noOpenShift',
    SHIFT_CLOSE_IN_PROGRESS: 'shiftClosing',
    METHOD_NOT_CONFIGURED: 'methodNotConfigured',
    ORDER_ALREADY_PAID: 'alreadyPaid',
    ORDER_PAYMENT_IN_PROGRESS: 'paymentInProgress',
    IDEMPOTENCY_KEY_CONFLICT: 'idempotencyConflict',
    PAYMENT_ALLOCATION_MISMATCH: 'allocationMismatch',
    INVENTORY_BUSY: 'inventoryBusy',
    INVENTORY_CONFIGURATION_ERROR: 'inventoryConfiguration',
    FINANCIAL_CONFIGURATION_ERROR: 'financialConfiguration',
    INVALID_PAYMENT_METHOD: 'invalidMethod',
    INVALID_ORDER_TOTAL: 'invalidTotal',
  }
  if (code && known[code]) return t(`backoffice.pos.payment.errors.${known[code]}`)
  if (typeof detail === 'string' && detail.trim()) return detail
  return typeof detail?.message === 'string' && detail.message.trim()
    ? detail.message
    : t('backoffice.pos.payment.errors.generic')
}

async function loadCheckedInRooms() {
  roomsLoading.value = true
  roomsError.value = ''
  try {
    const roomsResponse = await api.get(ENDPOINTS.pms.rooms, {
      params: { branch_id: props.branchId },
    })
    const roomData = roomsResponse.data
    const rooms: PMSRoom[] = roomData?.rooms ?? roomData?.items ?? roomData ?? []
    const roomsById = new Map(rooms.map(room => [room.id, room]))

    const bookings: CheckedInBooking[] = []
    let page = 1
    const pageSize = 100
    while (true) {
      const response = await api.get(ENDPOINTS.pms.bookings, {
        params: {
          branch_id: props.branchId,
          status: 'checked_in',
          page,
          size: pageSize,
        },
      })
      const pageItems: CheckedInBooking[] = response.data?.items ?? response.data ?? []
      bookings.push(...pageItems)
      if (!response.data?.items || pageItems.length < pageSize) break
      page += 1
    }

    checkedInRooms.value = bookings.flatMap(booking =>
      (booking.rooms ?? []).flatMap(bookingRoom => {
        const room = roomsById.get(bookingRoom.room_id)
        return room ? [{
          id: room.id,
          name: room.name,
          guestName: booking.guest_name,
          bookingNumber: booking.booking_number,
          checkOut: booking.check_out,
        }] : []
      }),
    ).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
    roomsLoaded.value = true
  } catch {
    roomsError.value = t('backoffice.pos.payment.errors.loadRooms')
  } finally {
    roomsLoading.value = false
  }
}

function selectCashPreset(minor: number) {
  cashReceived.value = minorToMoney(minor)
}

function addSplitRow() {
  if (splitRows.value.length >= 10) return
  splitRows.value.push({
    key: nextSplitKey++,
    paymentMethod: 'cash',
    amount: '',
    roomId: '',
    cashCurrency: 'EGP',
  })
}

function removeSplitRow(key: number) {
  if (splitRows.value.length <= 2) return
  splitRows.value = splitRows.value.filter(row => row.key !== key)
}

function fillSplitRemaining(row: SplitRow) {
  const otherAmounts = splitRows.value.filter(item => item.key !== row.key).map(item => item.amount)
  const remaining = remainingMinor(props.order?.total ?? 0, otherAmounts)
  if (remaining !== null && remaining > 0) row.amount = minorToMoney(remaining)
}

function validateSinglePayment(): { chargeToRoomId?: number } | null {
  if (paymentMethod.value === 'cash') {
    if (cashCurrency.value === 'EGP') {
      // التحقق العادي بالجنيه
      if (receivedMinor.value === null || receivedMinor.value < totalMinor.value) {
        paymentError.value = t('backoffice.pos.payment.errors.cashInsufficient')
        return null
      }
    } else {
      // POS-03: تحقق بالعملة الأجنبية
      if (currentFxRate.value <= 0) {
        paymentError.value = t('backoffice.pos.payment.errors.noFxRate', { currency: cashCurrency.value })
        return null
      }
      const received = parseFloat(foreignReceived.value)
      if (isNaN(received) || totalInForeignCurrency.value === null || received < totalInForeignCurrency.value) {
        paymentError.value = t('backoffice.pos.payment.errors.cashInsufficient')
        return null
      }
    }
  }
  if (paymentMethod.value === 'room') {
    const roomId = Number(selectedRoomId.value)
    if (!checkedInRooms.value.some(room => room.id === roomId)) {
      paymentError.value = t('backoffice.pos.payment.errors.selectCheckedInRoom')
      return null
    }
    return { chargeToRoomId: roomId }
  }
  return {}
}

async function paySingle() {
  if (!props.order) return
  paymentError.value = ''
  const validation = validateSinglePayment()
  if (validation === null) return
  const intent = `single:${props.order.id}:${paymentMethod.value}:${cashCurrency.value}:${validation.chargeToRoomId ?? ''}`
  const key = ensureIdempotencyKey(intent)
  busy.value = true

  // POS-03: بناء payload مع العملة/سعر الصرف للكاش الأجنبي
  const payload: Record<string, unknown> = {
    status: 'paid',
    payment_method: paymentMethod.value,
    charge_to_room_id: validation.chargeToRoomId,
  }
  if (paymentMethod.value === 'cash' && cashCurrency.value !== 'EGP' && currentFxRate.value > 0) {
    payload.payment_currency = cashCurrency.value
    payload.payment_fx_rate = currentFxRate.value
  }

  try {
    const { data } = await api.patch(
      ENDPOINTS.dining.orderStatus(props.order.id),
      payload,
      { headers: { 'Idempotency-Key': key } },
    )
    pendingKey.value = ''
    pendingIntent.value = ''
    emit('paid', data)
  } catch (error: any) {
    resetIdempotencyForFinalRejection(error)
    paymentError.value = paymentErrorMessage(error)
  } finally {
    busy.value = false
  }
}

function buildSplitPayments() {
  const payments: Array<{
    amount: string
    payment_method: PaymentMethod
    charge_to_room_id?: number
    currency?: string
    fx_rate?: number
  }> = []
  for (const row of splitRows.value) {
    const amountMinor = moneyToMinor(row.amount)
    if (amountMinor === null || amountMinor <= 0) {
      paymentError.value = t('backoffice.pos.payment.errors.splitPositive')
      return null
    }
    let chargeToRoomId: number | undefined
    if (row.paymentMethod === 'room') {
      const roomId = Number(row.roomId)
      if (!checkedInRooms.value.some(room => room.id === roomId)) {
        paymentError.value = t('backoffice.pos.payment.errors.selectRoomForEach')
        return null
      }
      chargeToRoomId = roomId
    }
    // POS-03: عملة الكاش الأجنبي
    const rowCur = row.cashCurrency || 'EGP'
    const rowFx = rowCur !== 'EGP' ? (fxRates.value[rowCur] ?? 0) : 0
    if (row.paymentMethod === 'cash' && rowCur !== 'EGP' && rowFx <= 0) {
      paymentError.value = t('backoffice.pos.payment.errors.noFxRate', { currency: rowCur })
      return null
    }
    payments.push({
      amount: minorToMoney(amountMinor),
      payment_method: row.paymentMethod,
      ...(chargeToRoomId ? { charge_to_room_id: chargeToRoomId } : {}),
      ...(row.paymentMethod === 'cash' && rowCur !== 'EGP' ? { currency: rowCur, fx_rate: rowFx } : {}),
    })
  }
  if (splitRemainingMinor.value !== 0) {
    paymentError.value = t('backoffice.pos.payment.errors.splitMismatch')
    return null
  }
  return payments
}

async function paySplit() {
  if (!props.order) return
  paymentError.value = ''
  const payments = buildSplitPayments()
  if (!payments) return
  const intent = `split:${props.order.id}:${JSON.stringify(payments)}`
  const key = ensureIdempotencyKey(intent)
  busy.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.dining.orderSplitBill(props.order.id),
      { payments },
      { headers: { 'Idempotency-Key': key } },
    )
    pendingKey.value = ''
    pendingIntent.value = ''
    emit('paid', data)
  } catch (error: any) {
    resetIdempotencyForFinalRejection(error)
    paymentError.value = paymentErrorMessage(error)
  } finally {
    busy.value = false
  }
}

function submitPayment() {
  if (mode.value === 'single') paySingle()
  else paySplit()
}
</script>

<template>
  <AppModal
    :open="open"
    :title="t('backoffice.pos.payment.title')"
    size="xl"
    :close-label="t('backoffice.pos.close')"
    @close="emit('close')"
  >
    <div v-if="order" class="space-y-5">
      <div class="rounded-2xl bg-primary-950 text-white p-5 flex items-center justify-between gap-4">
        <div>
          <div class="text-sm text-primary-100">{{ t('backoffice.pos.payment.amountDue') }}</div>
          <div class="text-sm text-primary-200 mt-1">{{ order.order_number }}</div>
        </div>
        <div class="text-3xl sm:text-4xl font-black tabular-nums">
          {{ formatMoney(order.total, currency) }}
        </div>
      </div>

      <div class="grid grid-cols-2 gap-2" role="tablist" :aria-label="t('backoffice.pos.payment.paymentMode')">
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'single'"
          :class="[
            'min-h-[48px] rounded-xl border-2 font-bold transition-colors',
            mode === 'single' ? 'border-primary-700 bg-primary-50 text-primary-800' : 'border-stone-200 text-gray-600 dark:text-gray-300',
          ]"
          @click="mode = 'single'; paymentError = ''"
        >
          {{ t('backoffice.pos.payment.single') }}
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'split'"
          :class="[
            'min-h-[48px] rounded-xl border-2 font-bold transition-colors',
            mode === 'split' ? 'border-primary-700 bg-primary-50 text-primary-800' : 'border-stone-200 text-gray-600 dark:text-gray-300',
          ]"
          @click="mode = 'split'; paymentError = ''"
        >
          {{ t('backoffice.pos.payment.split') }}
        </button>
      </div>

      <template v-if="mode === 'single'">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <button
            v-for="method in methodOptions"
            :key="method.value"
            type="button"
            :aria-pressed="paymentMethod === method.value"
            :class="[
              'min-h-[72px] rounded-xl border-2 px-3 py-2 font-bold transition-all flex flex-col items-center justify-center gap-1',
              paymentMethod === method.value
                ? 'border-primary-700 bg-primary-50 text-primary-800 shadow-sm'
                : 'border-stone-200 text-gray-600 dark:text-gray-300 hover:border-primary-300',
            ]"
            @click="paymentMethod = method.value; paymentError = ''"
          >
            <span class="text-xl" aria-hidden="true">{{ method.icon }}</span>
            <span>{{ method.label }}</span>
          </button>
        </div>

        <div v-if="paymentMethod === 'cash'" class="rounded-2xl border border-stone-200 dark:border-border p-4 space-y-4">
          <!-- POS-03: اختيار عملة الكاش -->
          <div class="flex flex-wrap gap-2 items-center">
            <span class="text-sm font-semibold text-gray-700 dark:text-gray-300">{{ t('backoffice.pos.payment.cashCurrency') }}</span>
            <div class="flex gap-2 flex-wrap">
              <button
                v-for="opt in currencyOptions"
                :key="opt.value"
                type="button"
                :aria-pressed="cashCurrency === opt.value"
                :class="[
                  'px-3 py-1.5 rounded-lg border-2 text-sm font-bold transition-colors',
                  cashCurrency === opt.value
                    ? 'border-primary-700 bg-primary-50 text-primary-800'
                    : 'border-stone-200 text-gray-600 hover:border-primary-300 dark:border-border dark:text-gray-300',
                ]"
                @click="cashCurrency = (opt.value as CashCurrency); foreignReceived = ''; paymentError = ''"
              >
                {{ opt.label }}
              </button>
            </div>
            <span v-if="fxLoading" class="text-xs text-gray-400">{{ t('backoffice.pos.payment.loadingRate') }}</span>
            <span v-else-if="cashCurrency !== 'EGP' && currentFxRate > 0" class="text-xs text-gray-500 dark:text-gray-400">
              1 {{ cashCurrency }} = {{ currentFxRate }} EGP
            </span>
            <span v-else-if="cashCurrency !== 'EGP'" class="text-xs text-danger">
              {{ t('backoffice.pos.payment.errors.noFxRate', { currency: cashCurrency }) }}
            </span>
          </div>

          <!-- كاش EGP عادي -->
          <template v-if="cashCurrency === 'EGP'">
            <MoneyInput
              v-model="cashReceived"
              :label="t('backoffice.pos.payment.cashReceived')"
              currency="EGP"
            />
            <div class="flex flex-wrap gap-2">
              <button
                v-for="preset in cashPresets"
                :key="preset"
                type="button"
                class="min-h-[44px] px-4 rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface font-bold tabular-nums hover:border-primary-400"
                @click="selectCashPreset(preset)"
              >
                {{ formatMoney(minorToMoney(preset), currency) }}
              </button>
            </div>
            <div
              :class="[
                'rounded-xl px-4 py-3 flex items-center justify-between font-bold',
                cashChangeMinor !== null && cashChangeMinor >= 0
                  ? 'bg-success/10 text-success'
                  : 'bg-danger/10 text-danger',
              ]"
            >
              <span>{{ t('backoffice.pos.payment.changeDue') }}</span>
              <span class="text-xl tabular-nums">
                {{ cashChangeMinor === null ? '—' : formatMoney(minorToMoney(Math.max(0, cashChangeMinor)), currency) }}
              </span>
            </div>
          </template>

          <!-- POS-03: كاش بعملة أجنبية -->
          <template v-else>
            <div class="rounded-xl bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 px-4 py-3 text-sm space-y-1">
              <div class="font-bold">{{ t('backoffice.pos.payment.foreignCashHint') }}</div>
              <div class="tabular-nums">
                {{ t('backoffice.pos.payment.requiredInForeign', {
                  amount: totalInForeignCurrency?.toFixed(2) ?? '—',
                  currency: cashCurrency,
                  rate: currentFxRate,
                }) }}
              </div>
            </div>
            <div>
              <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
                {{ t('backoffice.pos.payment.foreignReceivedLabel', { currency: cashCurrency }) }}
              </label>
              <input
                v-model="foreignReceived"
                type="number"
                step="0.01"
                min="0"
                class="w-full rounded-xl border-2 border-stone-200 dark:border-border bg-white dark:bg-surface px-4 py-3 text-lg font-bold tabular-nums focus:outline-none focus:border-primary-500"
                :placeholder="totalInForeignCurrency?.toFixed(2) ?? '0.00'"
                inputmode="decimal"
              />
            </div>
            <div
              v-if="foreignChangeMinor !== null"
              :class="[
                'rounded-xl px-4 py-3 flex items-center justify-between font-bold',
                foreignChangeMinor >= 0 ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger',
              ]"
            >
              <span>{{ t('backoffice.pos.payment.changeDueIn', { currency: 'EGP' }) }}</span>
              <span class="text-xl tabular-nums">
                {{ foreignChangeMinor >= 0
                  ? formatMoney(String(+(foreignChangeMinor * currentFxRate).toFixed(2)), 'EGP')
                  : '—' }}
              </span>
            </div>
          </template>
        </div>

        <div v-if="paymentMethod === 'room'" class="rounded-2xl border border-stone-200 dark:border-border p-4 space-y-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h3 class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.pos.payment.checkedInRoom') }}</h3>
              <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.pos.payment.roomOnlyHint') }}</p>
            </div>
            <AppButton variant="ghost" size="sm" :loading="roomsLoading" @click="loadCheckedInRooms">
              {{ t('backoffice.pos.payment.refreshRooms') }}
            </AppButton>
          </div>
          <SearchInput
            v-model="roomSearch"
            :placeholder="t('backoffice.pos.payment.searchRoom')"
            :clear-label="t('backoffice.pos.payment.clearRoomSearch')"
          />
          <LoadingState v-if="roomsLoading" size="sm" :label="t('backoffice.pos.payment.loadingRooms')" />
          <p v-else-if="roomsError" role="alert" class="text-sm text-danger">{{ roomsError }}</p>
          <EmptyState
            v-else-if="filteredRooms.length === 0"
            icon="🛏️"
            :title="t('backoffice.pos.payment.noCheckedInRooms')"
          />
          <div v-else class="grid sm:grid-cols-2 gap-2 max-h-56 overflow-y-auto">
            <button
              v-for="room in filteredRooms"
              :key="room.id"
              type="button"
              :aria-pressed="selectedRoomId === String(room.id)"
              :class="[
                'min-h-[64px] rounded-xl border-2 px-3 py-2 text-start transition-colors',
                selectedRoomId === String(room.id)
                  ? 'border-primary-700 bg-primary-50'
                  : 'border-stone-200 dark:border-border hover:border-primary-300',
              ]"
              @click="selectedRoomId = String(room.id)"
            >
              <div class="font-black text-gray-900 dark:text-gray-100">{{ room.name }}</div>
              <div class="text-sm text-gray-600 dark:text-gray-300">{{ room.guestName }}</div>
              <div class="text-xs text-gray-400">{{ room.bookingNumber }}</div>
            </button>
          </div>
        </div>

        <div v-if="paymentMethod === 'card' || paymentMethod === 'wallet'" class="rounded-xl bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 px-4 py-3 text-sm">
          {{ t('backoffice.pos.payment.configuredMethodHint') }}
        </div>
      </template>

      <template v-else>
        <div class="space-y-3">
          <div
            v-for="(row, index) in splitRows"
            :key="row.key"
            class="rounded-2xl border border-stone-200 dark:border-border p-4"
          >
            <div class="flex items-center justify-between gap-3 mb-3">
              <div class="flex items-center gap-2">
                <AppBadge variant="info">{{ index + 1 }}</AppBadge>
                <span class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.pos.payment.tender') }}</span>
              </div>
              <AppButton
                v-if="splitRows.length > 2"
                variant="ghost"
                size="sm"
                @click="removeSplitRow(row.key)"
              >
                {{ t('backoffice.pos.payment.removeTender') }}
              </AppButton>
            </div>
            <div class="grid sm:grid-cols-[1fr_1fr_auto] gap-3 items-end">
              <AppSelect
                :model-value="row.paymentMethod"
                :label="t('backoffice.pos.payment.method')"
                :options="methodOptions.map(method => ({ value: method.value, label: `${method.icon} ${method.label}` }))"
                @update:model-value="row.paymentMethod = ($event as PaymentMethod); row.roomId = ''; row.cashCurrency = 'EGP'; paymentError = ''"
              />
              <MoneyInput
                v-model="row.amount"
                :label="t('backoffice.pos.payment.amount')"
                currency="EGP"
              />
              <AppButton variant="outline" size="sm" class="min-h-[44px]" @click="fillSplitRemaining(row)">
                {{ t('backoffice.pos.payment.fillRemaining') }}
              </AppButton>
            </div>
            <!-- POS-03: اختيار عملة الكاش في split -->
            <div v-if="row.paymentMethod === 'cash'" class="mt-3 flex flex-wrap gap-2 items-center">
              <span class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.pos.payment.cashCurrency') }}:</span>
              <button
                v-for="opt in currencyOptions"
                :key="opt.value"
                type="button"
                :aria-pressed="(row.cashCurrency || 'EGP') === opt.value"
                :class="[
                  'px-2 py-1 rounded-lg border text-xs font-bold transition-colors',
                  (row.cashCurrency || 'EGP') === opt.value
                    ? 'border-primary-700 bg-primary-50 text-primary-800'
                    : 'border-stone-200 text-gray-600 hover:border-primary-300 dark:border-border dark:text-gray-300',
                ]"
                @click="row.cashCurrency = (opt.value as CashCurrency); paymentError = ''"
              >
                {{ opt.label }}
              </button>
            </div>
            <AppSelect
              v-if="row.paymentMethod === 'room'"
              :model-value="row.roomId"
              class="mt-3"
              :label="t('backoffice.pos.payment.checkedInRoom')"
              :placeholder="t('backoffice.pos.payment.selectRoom')"
              :options="roomOptions"
              @update:model-value="row.roomId = String($event)"
            />
          </div>
          <AppButton
            variant="outline"
            block
            :disabled="splitRows.length >= 10"
            @click="addSplitRow"
          >
            {{ t('backoffice.pos.payment.addTender') }}
          </AppButton>
        </div>

        <div
          :class="[
            'rounded-xl px-4 py-3 flex items-center justify-between font-bold',
            splitRemainingMinor === 0
              ? 'bg-success/10 text-success'
              : splitRemainingMinor > 0
                ? 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300'
                : 'bg-danger/10 text-danger',
          ]"
        >
          <span>{{ splitRemainingMinor >= 0 ? t('backoffice.pos.payment.remaining') : t('backoffice.pos.payment.overAllocated') }}</span>
          <span class="text-xl tabular-nums">{{ formatMoney(minorToMoney(Math.abs(splitRemainingMinor)), currency) }}</span>
        </div>
      </template>

      <p v-if="paymentError" role="alert" class="rounded-xl bg-danger/10 text-danger px-4 py-3 text-sm font-semibold">
        {{ paymentError }}
      </p>
    </div>

    <template #footer>
      <div class="flex flex-col-reverse sm:flex-row gap-2">
        <AppButton variant="ghost" size="lg" @click="emit('close')">
          {{ t('backoffice.pos.close') }}
        </AppButton>
        <AppButton
          variant="primary"
          size="lg"
          block
          :loading="busy"
          :disabled="!order || (mode === 'split' && splitRemainingMinor !== 0)"
          @click="submitPayment"
        >
          {{ t('backoffice.pos.payment.confirmPayment', { amount: order ? formatMoney(order.total, currency) : '—' }) }}
        </AppButton>
      </div>
    </template>
  </AppModal>
</template>

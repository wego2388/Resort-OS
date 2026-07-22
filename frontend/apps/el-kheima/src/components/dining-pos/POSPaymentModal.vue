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

interface SplitRow {
  key: number
  paymentMethod: PaymentMethod
  amount: string
  roomId: string
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
  branchId: number
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
    { key: 1, paymentMethod: 'cash', amount: '', roomId: '' },
    { key: 2, paymentMethod: 'card', amount: '', roomId: '' },
  ]
}

function resetPaymentState() {
  mode.value = 'single'
  paymentMethod.value = 'cash'
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
    if (receivedMinor.value === null || receivedMinor.value < totalMinor.value) {
      paymentError.value = t('backoffice.pos.payment.errors.cashInsufficient')
      return null
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
  const intent = `single:${props.order.id}:${paymentMethod.value}:${validation.chargeToRoomId ?? ''}`
  const key = ensureIdempotencyKey(intent)
  busy.value = true
  try {
    const { data } = await api.patch(
      ENDPOINTS.dining.orderStatus(props.order.id),
      {
        status: 'paid',
        payment_method: paymentMethod.value,
        charge_to_room_id: validation.chargeToRoomId,
      },
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
    payments.push({
      amount: minorToMoney(amountMinor),
      payment_method: row.paymentMethod,
      ...(chargeToRoomId ? { charge_to_room_id: chargeToRoomId } : {}),
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
                @update:model-value="row.paymentMethod = ($event as PaymentMethod); row.roomId = ''; paymentError = ''"
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

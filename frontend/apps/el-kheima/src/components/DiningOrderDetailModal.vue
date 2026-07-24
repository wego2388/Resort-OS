<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { useOrderDiscount } from '@resort-os/core/composables'
import {
  AppBadge,
  AppButton,
  AppDrawer,
  AppSelect,
  AppTextarea,
  LoadingState,
  StatusBadge,
} from '@resort-os/ui'
import type { SelectOption } from '@resort-os/ui'
import PinGuardModal from './PinGuardModal.vue'
import POSPaymentModal from './dining-pos/POSPaymentModal.vue'
import StepUpConfirmModal from './StepUpConfirmModal.vue'
import type { DiningOrderDetail, OrderItem, VenueTable } from './dining-pos/types'

const props = defineProps<{
  orderId: number | null
  tables?: VenueTable[]
  branchId: number
}>()
const emit = defineEmits<{ close: []; changed: [] }>()

const { t } = useI18n()
const { formatDateTime, formatMoney } = useStaffFormat()
const auth = useAuthStore()
const currency = 'EGP'

const canVoid = computed(() => auth.hasRole('cashier'))
const canRefund = computed(() => auth.hasRole('manager'))
const canApplyDiscount = computed(() => auth.hasRole('cashier'))
const canCompletePayment = computed(() => auth.hasRole('cashier'))
const canTransferTable = computed(() => auth.hasRole('waiter'))

const order = ref<DiningOrderDetail | null>(null)
const loading = ref(false)
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const paymentOpen = ref(false)

const transferOpen = ref(false)
const transferTableId = ref('')
const transferError = ref('')
const mergeOpen = ref(false)
const mergeTargetOrderId = ref('')
const mergeError = ref('')

const voidingItemId = ref<number | null>(null)
const voidReason = ref('')
const voidError = ref('')
const showVoidPinGuard = ref(false)

const pendingRefundItemId = ref<number | null>(null)
const refundStepUpBusy = ref(false)
const refundStepUpError = ref('')

const { applyingDiscount, discountError, applyDiscount: applyDiscountRule } = useOrderDiscount()
const showDiscountPinGuard = ref(false)

const statusMap = computed(() => ({
  held: { label: t('backoffice.pos.orderStatus.held'), variant: 'warning' as const },
  open: { label: t('backoffice.pos.orderStatus.open'), variant: 'info' as const },
  in_kitchen: { label: t('backoffice.pos.orderStatus.inKitchen'), variant: 'info' as const },
  served: { label: t('backoffice.pos.orderStatus.served'), variant: 'warning' as const },
  paid: { label: t('backoffice.pos.orderStatus.paid'), variant: 'success' as const },
  cancelled: { label: t('backoffice.pos.orderStatus.cancelled'), variant: 'danger' as const },
  refunded: { label: t('backoffice.pos.orderStatus.refunded'), variant: 'danger' as const },
}))

const tableLabel = computed(() => {
  if (!order.value) return ''
  if (!order.value.table_id) {
    const key = {
      dine_in: 'dineIn',
      takeaway: 'takeaway',
      delivery: 'delivery',
      room_service: 'roomService',
    }[order.value.order_type]
    return t(`backoffice.pos.orderTypes.${key}`)
  }
  const table = (props.tables ?? []).find(item => item.id === order.value?.table_id)
  return t('backoffice.pos.tableLabel', { number: table?.table_number ?? order.value.table_id })
})

const transferOptions = computed<SelectOption[]>(() => (props.tables ?? [])
  .filter(table => table.id !== order.value?.table_id)
  .map(table => ({
    value: table.id,
    label: `${t('backoffice.pos.tableLabel', { number: table.table_number })} — ${tableStatusLabel(table.status)}`,
    disabled: table.status === 'occupied' || table.status === 'served' || table.status === 'out_of_service',
  })))

const mergeOptions = computed<SelectOption[]>(() => (props.tables ?? [])
  .filter(table =>
    table.status === 'occupied' &&
    table.active_order_id &&
    table.active_order_id !== order.value?.id,
  )
  .map(table => ({
    value: table.active_order_id!,
    label: t('backoffice.pos.orderDetail.mergeOption', {
      table: table.table_number,
      order: table.active_order_number,
    }),
  })))

const canMerge = computed(() =>
  auth.hasRole('waiter') &&
  order.value?.order_type === 'dine_in' &&
  !['paid', 'cancelled'].includes(order.value?.status ?? ''),
)

function tableStatusLabel(status: string): string {
  const key: Record<string, string> = {
    available: 'available',
    occupied: 'occupied',
    served: 'served',
    reserved: 'reserved',
    out_of_service: 'outOfService',
  }
  return key[status] ? t(`backoffice.pos.tableStatus.${key[status]}`) : status
}

function apiMessage(error: any, fallbackKey: string): string {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (typeof detail?.message === 'string' && detail.message.trim()) return detail.message
  return t(fallbackKey)
}

function showSuccess(message: string) {
  successMessage.value = message
  setTimeout(() => {
    if (successMessage.value === message) successMessage.value = ''
  }, 2500)
}

async function loadOrder() {
  paymentOpen.value = false
  if (!props.orderId) {
    order.value = null
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const { data } = await api.get(ENDPOINTS.dining.order(props.orderId))
    order.value = data
  } catch (error: any) {
    errorMessage.value = apiMessage(error, 'backoffice.pos.orderDetail.errors.load')
  } finally {
    loading.value = false
  }
}

watch(() => props.orderId, loadOrder, { immediate: true })

function openTransferPrompt() {
  transferOpen.value = true
  transferTableId.value = ''
  transferError.value = ''
}

function cancelTransferPrompt() {
  transferOpen.value = false
  transferTableId.value = ''
  transferError.value = ''
}

async function confirmTransfer() {
  if (!order.value || !Number(transferTableId.value)) {
    transferError.value = t('backoffice.pos.orderDetail.errors.selectNewTable')
    return
  }
  busy.value = true
  try {
    const { data } = await api.patch(
      ENDPOINTS.dining.orderTransfer(order.value.id),
      { table_id: Number(transferTableId.value) },
    )
    order.value = data
    cancelTransferPrompt()
    showSuccess(t('backoffice.pos.orderDetail.messages.transferred'))
    emit('changed')
  } catch (error: any) {
    transferError.value = apiMessage(error, 'backoffice.pos.orderDetail.errors.transfer')
  } finally {
    busy.value = false
  }
}

function openMergePrompt() {
  mergeOpen.value = true
  mergeTargetOrderId.value = ''
  mergeError.value = ''
}

function cancelMergePrompt() {
  mergeOpen.value = false
  mergeTargetOrderId.value = ''
  mergeError.value = ''
}

async function confirmMerge() {
  if (!order.value || !Number(mergeTargetOrderId.value)) {
    mergeError.value = t('backoffice.pos.orderDetail.errors.selectMergeTable')
    return
  }
  busy.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.dining.orderMerge(order.value.id),
      null,
      { params: { target_order_id: Number(mergeTargetOrderId.value) } },
    )
    order.value = data
    cancelMergePrompt()
    showSuccess(t('backoffice.pos.orderDetail.messages.merged'))
    emit('changed')
  } catch (error: any) {
    mergeError.value = apiMessage(error, 'backoffice.pos.orderDetail.errors.merge')
  } finally {
    busy.value = false
  }
}

function openVoidPrompt(itemId: number) {
  voidingItemId.value = itemId
  voidReason.value = ''
  voidError.value = ''
}

function cancelVoidPrompt() {
  voidingItemId.value = null
  voidReason.value = ''
  voidError.value = ''
  showVoidPinGuard.value = false
}

function requestVoid() {
  if (voidReason.value.trim().length < 3) {
    voidError.value = t('backoffice.pos.orderDetail.errors.reasonTooShort')
    return
  }
  voidError.value = ''
  showVoidPinGuard.value = true
}

async function onVoidPinApproved(approval: { approverUserId: number | null; approverPin: string | null }) {
  if (!order.value || voidingItemId.value === null) return
  busy.value = true
  try {
    const { data } = await api.patch(
      ENDPOINTS.dining.orderItemVoid(order.value.id, voidingItemId.value),
      {
        reason: voidReason.value.trim(),
        ...(approval.approverUserId ? {
          approver_user_id: approval.approverUserId,
          approver_pin: approval.approverPin,
        } : {}),
      },
    )
    order.value = data
    cancelVoidPrompt()
    showSuccess(t('backoffice.pos.orderDetail.messages.itemVoided'))
    emit('changed')
  } catch (error: any) {
    showVoidPinGuard.value = false
    voidError.value = apiMessage(error, 'backoffice.pos.orderDetail.errors.voidItem')
  } finally {
    busy.value = false
  }
}

function openRefundPrompt(itemId: number) {
  pendingRefundItemId.value = itemId
  refundStepUpError.value = ''
}

function cancelRefundPrompt() {
  pendingRefundItemId.value = null
  refundStepUpError.value = ''
}

async function onRefundStepUpConfirmed(payload: { stepUpToken: string; reason: string }) {
  if (!order.value || pendingRefundItemId.value === null) return
  refundStepUpBusy.value = true
  try {
    const { data } = await api.patch(
      ENDPOINTS.dining.orderItemRefund(order.value.id, pendingRefundItemId.value),
      { reason: payload.reason },
      { headers: { 'X-Step-Up-Token': payload.stepUpToken } },
    )
    order.value = data
    cancelRefundPrompt()
    showSuccess(t('backoffice.pos.orderDetail.messages.itemRefunded'))
    emit('changed')
  } catch (error: any) {
    const code = error?.response?.data?.detail?.error_code
    refundStepUpError.value = code === 'STEP_UP_INVALID'
      ? t('backoffice.pos.orderDetail.errors.stepUpInvalid')
      : apiMessage(error, 'backoffice.pos.orderDetail.errors.refundItem')
  } finally {
    refundStepUpBusy.value = false
  }
}

function requestDiscount() {
  showDiscountPinGuard.value = true
}

async function onDiscountPinApproved(approval: { approverUserId: number | null; approverPin: string | null }) {
  showDiscountPinGuard.value = false
  if (!order.value) return
  try {
    const data = await applyDiscountRule(order.value.id, approval)
    order.value = data
    showSuccess(Number(data.discount_amount) > 0
      ? t('backoffice.pos.orderDetail.messages.discountApplied', {
        amount: formatMoney(data.discount_amount, currency),
      })
      : t('backoffice.pos.noActiveDiscountRule'))
    emit('changed')
  } catch {
    // The composable exposes the error directly below the action.
  }
}

async function setStatus(status: string) {
  if (!order.value) return
  const { data } = await api.patch(ENDPOINTS.dining.orderStatus(order.value.id), { status })
  order.value = data
}

async function resumeAndSend() {
  if (!order.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    if (order.value.status === 'held') await setStatus('open')
    await setStatus('in_kitchen')
    showSuccess(t('backoffice.pos.orderDetail.messages.sent'))
    emit('changed')
  } catch (error: any) {
    errorMessage.value = apiMessage(error, 'backoffice.pos.orderDetail.errors.send')
  } finally {
    busy.value = false
  }
}

async function markServed() {
  if (!order.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    await setStatus('served')
    showSuccess(t('backoffice.pos.orderDetail.messages.served'))
    emit('changed')
  } catch (error: any) {
    errorMessage.value = apiMessage(error, 'backoffice.pos.orderDetail.errors.status')
  } finally {
    busy.value = false
  }
}

function onPaymentCompleted(paidOrder: DiningOrderDetail) {
  order.value = paidOrder
  paymentOpen.value = false
  showSuccess(t('backoffice.pos.orderDetail.messages.paid'))
  emit('changed')
}

function lineTotal(item: OrderItem): number {
  if (item.status === 'cancelled' || item.status === 'refunded') return 0
  const extras = item.extras.reduce((sum, extra) => sum + Number(extra.price_addition), 0)
  return (Number(item.unit_price) + extras) * item.quantity
}

function paymentMethodLabel(method: string): string {
  if (method === 'split') return t('backoffice.pos.payment.split')
  const known = ['cash', 'card', 'room', 'wallet']
  return known.includes(method) ? t(`backoffice.pos.payment.methods.${method}`) : method
}
</script>

<template>
  <AppDrawer
    :open="!!orderId"
    :title="t('backoffice.pos.orderDetail.title')"
    width="lg"
    @close="emit('close')"
  >
    <LoadingState v-if="loading" :label="t('backoffice.pos.orderDetail.loading')" />

    <div v-else-if="order" class="space-y-5">
      <section class="rounded-2xl bg-primary-950 text-white p-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-2xl font-black">{{ order.order_number }}</div>
            <div class="text-primary-100 font-semibold mt-1">{{ tableLabel }}</div>
            <div class="text-sm text-primary-200 mt-2">
              {{ formatDateTime(order.created_at) }}
              <span v-if="order.guests_count > 0"> · {{ t('backoffice.pos.orderDetail.guests', { count: order.guests_count }) }}</span>
            </div>
          </div>
          <StatusBadge :status="order.status" :map="statusMap" />
        </div>
        <div class="flex items-end justify-between gap-3 mt-5 pt-4 border-t border-primary-800">
          <span class="text-primary-100">{{ t('backoffice.pos.total') }}</span>
          <span class="text-3xl font-black tabular-nums">{{ formatMoney(order.total, currency) }}</span>
        </div>
      </section>

      <section
        v-if="canTransferTable && order.order_type === 'dine_in' && !['paid', 'cancelled'].includes(order.status)"
        class="rounded-2xl border border-stone-200 dark:border-border p-4"
      >
        <button
          v-if="!transferOpen"
          type="button"
          class="min-h-[44px] font-bold text-primary-700 dark:text-primary-300"
          @click="openTransferPrompt"
        >
          🔀 {{ t('backoffice.pos.orderDetail.transferAction') }}
        </button>
        <div v-else class="space-y-3">
          <h3 class="font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.pos.orderDetail.transferTitle') }}</h3>
          <AppSelect
            v-model="transferTableId"
            :options="transferOptions"
            :placeholder="t('backoffice.pos.orderDetail.selectNewTable')"
            :error="transferError"
          />
          <div class="grid grid-cols-2 gap-2">
            <AppButton variant="ghost" @click="cancelTransferPrompt">{{ t('backoffice.pos.orderDetail.cancel') }}</AppButton>
            <AppButton :loading="busy" @click="confirmTransfer">{{ t('backoffice.pos.orderDetail.confirmTransfer') }}</AppButton>
          </div>
        </div>
      </section>

      <section
        v-if="canMerge"
        class="rounded-2xl border border-stone-200 dark:border-border p-4"
      >
        <button
          v-if="!mergeOpen"
          type="button"
          class="min-h-[44px] font-bold text-purple-700 dark:text-purple-300"
          @click="openMergePrompt"
        >
          🔗 {{ t('backoffice.pos.orderDetail.mergeAction') }}
        </button>
        <div v-else class="space-y-3">
          <div>
            <h3 class="font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.pos.orderDetail.mergeTitle') }}</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.pos.orderDetail.mergeHint') }}</p>
          </div>
          <AppSelect
            v-model="mergeTargetOrderId"
            :options="mergeOptions"
            :placeholder="t('backoffice.pos.orderDetail.selectMergeTable')"
            :error="mergeError"
          />
          <p v-if="mergeOptions.length === 0" class="text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.pos.orderDetail.noMergeTables') }}</p>
          <div class="grid grid-cols-2 gap-2">
            <AppButton variant="ghost" @click="cancelMergePrompt">{{ t('backoffice.pos.orderDetail.cancel') }}</AppButton>
            <AppButton :disabled="!mergeTargetOrderId" :loading="busy" @click="confirmMerge">{{ t('backoffice.pos.orderDetail.confirmMerge') }}</AppButton>
          </div>
        </div>
      </section>

      <section>
        <div class="flex items-center justify-between gap-3 mb-3">
          <h3 class="font-black text-gray-950 dark:text-gray-100">{{ t('backoffice.pos.orderDetail.itemsTitle') }}</h3>
          <AppBadge variant="neutral">{{ order.items.length }}</AppBadge>
        </div>
        <div class="space-y-2">
          <article
            v-for="item in order.items"
            :key="item.id"
            :class="[
              'rounded-2xl border p-4',
              ['cancelled', 'refunded'].includes(item.status)
                ? 'border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/50 opacity-70'
                : 'border-stone-200 dark:border-border bg-white dark:bg-surface',
            ]"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div :class="['font-bold text-gray-950 dark:text-gray-100', ['cancelled', 'refunded'].includes(item.status) ? 'line-through' : '']">
                  {{ item.quantity }}× {{ item.name }}
                </div>
                <div v-if="item.extras.length" class="text-sm text-gray-500 dark:text-gray-400 mt-2 space-y-1">
                  <div v-for="extra in item.extras" :key="extra.id">
                    {{ extra.extra_name }}<template v-if="extra.text_value">: {{ extra.text_value }}</template>
                  </div>
                </div>
                <div v-if="item.notes" class="text-sm text-gray-500 dark:text-gray-400 mt-2">📝 {{ item.notes }}</div>
                <div v-if="item.status === 'cancelled'" class="text-sm text-danger mt-2">
                  {{ t('backoffice.pos.orderDetail.itemCancelled') }}<template v-if="item.voided_reason"> — {{ item.voided_reason }}</template>
                </div>
                <div v-if="item.status === 'refunded'" class="text-sm text-danger mt-2">
                  {{ t('backoffice.pos.orderDetail.itemRefunded') }}<template v-if="item.voided_reason"> — {{ item.voided_reason }}</template>
                </div>
              </div>
              <div class="flex flex-col items-end gap-2 flex-shrink-0">
                <span class="font-black text-primary-800 dark:text-primary-300 tabular-nums">{{ formatMoney(lineTotal(item), currency) }}</span>
                <AppButton
                  v-if="canVoid && !['cancelled', 'refunded'].includes(item.status) && !['paid', 'cancelled'].includes(order.status)"
                  variant="ghost"
                  size="sm"
                  @click="openVoidPrompt(item.id)"
                >
                  {{ t('backoffice.pos.orderDetail.voidItem') }}
                </AppButton>
                <AppButton
                  v-if="canRefund && order.status === 'paid' && !['cancelled', 'refunded'].includes(item.status)"
                  variant="ghost"
                  size="sm"
                  :disabled="pendingRefundItemId !== null"
                  @click="openRefundPrompt(item.id)"
                >
                  {{ t('backoffice.pos.orderDetail.refundItem') }}
                </AppButton>
              </div>
            </div>

            <div v-if="voidingItemId === item.id" class="mt-4 pt-4 border-t border-stone-200 dark:border-border space-y-3">
              <AppTextarea
                v-model="voidReason"
                :rows="2"
                :placeholder="t('backoffice.pos.orderDetail.voidReasonPlaceholder')"
              />
              <p v-if="voidError" role="alert" class="text-sm text-danger">{{ voidError }}</p>
              <div class="grid grid-cols-2 gap-2">
                <AppButton variant="ghost" @click="cancelVoidPrompt">{{ t('backoffice.pos.orderDetail.cancel') }}</AppButton>
                <AppButton variant="danger" :loading="busy" @click="requestVoid">{{ t('backoffice.pos.orderDetail.confirmVoid') }}</AppButton>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="rounded-2xl border border-stone-200 dark:border-border p-4 space-y-2 text-sm">
        <div class="flex justify-between gap-3 text-gray-500 dark:text-gray-400">
          <span>{{ t('backoffice.pos.orderDetail.subtotal') }}</span><span class="tabular-nums">{{ formatMoney(order.subtotal, currency) }}</span>
        </div>
        <div class="flex justify-between gap-3 text-gray-500 dark:text-gray-400">
          <span>{{ t('backoffice.pos.orderDetail.vat') }}</span><span class="tabular-nums">{{ formatMoney(order.vat_amount, currency) }}</span>
        </div>
        <div class="flex justify-between gap-3 text-gray-500 dark:text-gray-400">
          <span>{{ t('backoffice.pos.orderDetail.service') }}</span><span class="tabular-nums">{{ formatMoney(order.service_charge, currency) }}</span>
        </div>
        <div v-if="Number(order.delivery_fee) > 0" class="flex justify-between gap-3 text-gray-500 dark:text-gray-400">
          <span>{{ t('backoffice.pos.orderDetail.deliveryFee') }}</span><span class="tabular-nums">{{ formatMoney(order.delivery_fee, currency) }}</span>
        </div>
        <div v-if="Number(order.discount_amount) > 0" class="flex justify-between gap-3 text-success font-semibold">
          <span>{{ t('backoffice.pos.orderDetail.discount') }}</span><span class="tabular-nums">−{{ formatMoney(order.discount_amount, currency) }}</span>
        </div>
        <div v-if="Number(order.refunded_amount) > 0" class="flex justify-between gap-3 text-danger font-semibold">
          <span>{{ t('backoffice.pos.orderDetail.refunds') }}</span><span class="tabular-nums">−{{ formatMoney(order.refunded_amount, currency) }}</span>
        </div>
        <div class="flex items-end justify-between gap-3 pt-3 border-t border-stone-200 dark:border-border">
          <span class="text-base font-black text-gray-950 dark:text-gray-100">{{ t('backoffice.pos.total') }}</span>
          <span class="text-2xl font-black text-primary-800 dark:text-primary-300 tabular-nums">{{ formatMoney(order.total, currency) }}</span>
        </div>
        <div v-if="order.status === 'paid' && order.payment_method" class="flex justify-between gap-3 pt-2 text-gray-500 dark:text-gray-400">
          <span>{{ t('backoffice.pos.orderDetail.paymentMethod') }}</span>
          <span class="font-bold text-gray-800 dark:text-gray-200">{{ paymentMethodLabel(order.payment_method) }}</span>
        </div>
      </section>

      <AppButton
        v-if="canApplyDiscount && !['paid', 'cancelled'].includes(order.status)"
        variant="secondary"
        block
        :loading="applyingDiscount"
        @click="requestDiscount"
      >
        🏷️ {{ t('backoffice.pos.applyDiscount') }}
      </AppButton>
      <p v-if="discountError" role="alert" class="text-sm text-danger">{{ discountError }}</p>

      <transition name="fade">
        <div v-if="successMessage" role="status" class="rounded-xl bg-success/10 text-success px-4 py-3 text-sm text-center font-bold">
          {{ successMessage }}
        </div>
      </transition>
      <transition name="fade">
        <div v-if="errorMessage" role="alert" class="rounded-xl bg-danger/10 text-danger px-4 py-3 text-sm text-center font-bold">
          {{ errorMessage }}
        </div>
      </transition>
    </div>

    <template v-if="order" #footer>
      <div class="grid grid-cols-2 gap-2">
        <AppButton variant="ghost" size="lg" @click="emit('close')">{{ t('backoffice.pos.close') }}</AppButton>
        <AppButton
          v-if="['held', 'open'].includes(order.status)"
          size="lg"
          :loading="busy"
          @click="resumeAndSend"
        >
          🍳 {{ t('backoffice.pos.sendToKitchen') }}
        </AppButton>
        <AppButton
          v-if="order.status === 'in_kitchen'"
          size="lg"
          :loading="busy"
          @click="markServed"
        >
          🍽️ {{ t('backoffice.pos.orderDetail.markServed') }}
        </AppButton>
        <AppButton
          v-if="['open', 'in_kitchen', 'served'].includes(order.status) && canCompletePayment"
          :class="order.status === 'served' ? 'col-span-2' : ''"
          size="lg"
          @click="paymentOpen = true"
        >
          💳 {{ t('backoffice.pos.orderDetail.collectPayment') }}
        </AppButton>
      </div>
    </template>
  </AppDrawer>

  <POSPaymentModal
    :open="paymentOpen"
    :order="order"
    :branch-id="branchId"
    @close="paymentOpen = false"
    @paid="onPaymentCompleted"
  />

  <PinGuardModal
    v-if="showVoidPinGuard"
    :min-level="60"
    :title="t('backoffice.pos.orderDetail.voidPinTitle')"
    :message="t('backoffice.pos.orderDetail.voidPinMessage')"
    :loading="busy"
    :error-message="voidError"
    @approved="onVoidPinApproved"
    @cancel="showVoidPinGuard = false"
  />

  <PinGuardModal
    v-if="showDiscountPinGuard"
    :min-level="60"
    :title="t('backoffice.pos.discountPinGuard.title')"
    :message="t('backoffice.pos.discountPinGuard.message')"
    :loading="applyingDiscount"
    :error-message="discountError"
    @approved="onDiscountPinApproved"
    @cancel="showDiscountPinGuard = false"
  />

  <StepUpConfirmModal
    v-if="pendingRefundItemId !== null && order"
    purpose="dining_refund"
    :intent="{ order_id: order.id, item_id: pendingRefundItemId }"
    :description="t('backoffice.pos.orderDetail.refundStepUpDescription')"
    :loading="refundStepUpBusy"
    :error-message="refundStepUpError"
    @confirmed="onRefundStepUpConfirmed"
    @cancel="cancelRefundPrompt"
  />
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>

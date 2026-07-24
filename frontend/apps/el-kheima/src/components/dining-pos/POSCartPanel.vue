<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppBadge, AppButton, AppTextarea, EmptyState, IconButton } from '@resort-os/ui'
import type { CartLine, OrderType, POSCustomer } from './types'

const props = defineProps<{
  cart: CartLine[]
  orderType: OrderType
  contextLabel: string
  covers: number
  note: string
  noteLabel: string
  cartLocked: boolean
  pendingOrderNumber: string
  itemSubtotal: number
  serverSummary: { discount_amount: number | string; total: number | string } | null
  customer: POSCustomer | null
  submitting: boolean
  applyingDiscount: boolean
  discountError: string
  online: boolean
}>()

const emit = defineEmits<{
  'update:covers': [value: number]
  'update:note': [value: string]
  quantity: [key: string, delta: number]
  remove: [key: string]
  clear: []
  discount: []
  customer: []
  send: []
  pay: []
}>()

const { t, locale } = useI18n()
const { formatMoney } = useStaffFormat()
const itemCount = computed(() => props.cart.reduce((sum, line) => sum + line.quantity, 0))
const displayedTotal = computed(() => props.serverSummary?.total ?? props.itemSubtotal)
const payPrimary = computed(() => props.orderType !== 'dine_in')
</script>

<template>
  <aside class="h-full min-h-0 bg-white dark:bg-surface border-s border-stone-200 dark:border-border flex flex-col shadow-sm">
    <div class="px-4 py-3 border-b border-stone-200 dark:border-border flex-shrink-0">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h2 class="font-black text-gray-950 dark:text-gray-100 truncate">{{ contextLabel }}</h2>
            <AppBadge variant="neutral" size="sm">{{ itemCount }}</AppBadge>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.pos.cart.orderInProgress') }}</p>
        </div>
        <IconButton
          icon="delete"
          :label="t('backoffice.pos.clear')"
          variant="danger"
          :disabled="cart.length === 0"
          @click="emit('clear')"
        />
      </div>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
      <div v-if="orderType === 'dine_in'" class="rounded-xl border border-stone-200 dark:border-border px-3 py-2 flex items-center justify-between gap-3">
        <span class="text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.pos.covers') }}</span>
        <div class="flex items-center gap-2">
          <IconButton
            icon="remove"
            :label="t('backoffice.pos.decreaseCovers')"
            :disabled="cartLocked || covers <= 1"
            @click="emit('update:covers', Math.max(1, covers - 1))"
          />
          <span class="w-8 text-center font-black text-lg tabular-nums">{{ covers }}</span>
          <IconButton
            icon="add"
            :label="t('backoffice.pos.increaseCovers')"
            :disabled="cartLocked"
            @click="emit('update:covers', covers + 1)"
          />
        </div>
      </div>

      <button
        type="button"
        class="w-full min-h-[52px] rounded-xl border border-dashed border-primary-300 bg-primary-50/60 dark:bg-primary-950/20 px-3 py-2 text-start hover:border-primary-500 transition-colors"
        @click="emit('customer')"
      >
        <template v-if="customer">
          <div class="flex items-center justify-between gap-2">
            <div class="min-w-0">
              <div class="text-xs text-primary-700 dark:text-primary-300">{{ t('backoffice.pos.customer.attached') }}</div>
              <div class="font-bold text-gray-900 dark:text-gray-100 truncate">{{ customer.full_name }}</div>
              <div v-if="customer.phone" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ customer.phone }}</div>
            </div>
            <span class="text-primary-700 dark:text-primary-300 text-sm font-bold">{{ t('backoffice.pos.customer.change') }}</span>
          </div>
        </template>
        <template v-else>
          <div class="font-bold text-primary-800 dark:text-primary-300">＋ {{ t('backoffice.pos.customer.add') }}</div>
          <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ t('backoffice.pos.customer.addHint') }}</div>
        </template>
      </button>

      <EmptyState
        v-if="cart.length === 0"
        icon="🛒"
        :title="t('backoffice.pos.cartEmpty')"
        :subtitle="t('backoffice.pos.cart.emptyHint')"
      />

      <div v-else class="space-y-2">
        <div
          v-for="line in cart"
          :key="line.key"
          class="rounded-xl border border-stone-200 dark:border-border p-3 bg-white dark:bg-surface"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="font-bold text-gray-900 dark:text-gray-100 leading-snug">
                {{ locale === 'ar' ? (line.nameAr || line.name) : line.name }}
              </div>
              <div v-if="line.variantLabel" class="text-xs text-primary-700 dark:text-primary-300 mt-1">{{ line.variantLabel }}</div>
              <div v-if="line.extrasLabel" class="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">{{ line.extrasLabel }}</div>
              <div v-if="line.notes" class="text-xs text-gray-500 dark:text-gray-400 mt-1">📝 {{ line.notes }}</div>
            </div>
            <IconButton
              icon="close"
              :label="t('backoffice.pos.removeItem')"
              variant="danger"
              size="sm"
              :disabled="cartLocked"
              @click="emit('remove', line.key)"
            />
          </div>
          <div class="flex items-center justify-between gap-3 mt-3">
            <div class="flex items-center gap-2">
              <IconButton
                icon="remove"
                :label="t('backoffice.pos.decreaseQty')"
                size="sm"
                :disabled="cartLocked"
                @click="emit('quantity', line.key, -1)"
              />
              <span class="w-7 text-center font-black tabular-nums">{{ line.quantity }}</span>
              <IconButton
                icon="add"
                :label="t('backoffice.pos.increaseQty')"
                size="sm"
                :disabled="cartLocked"
                @click="emit('quantity', line.key, 1)"
              />
            </div>
            <span class="font-black text-primary-800 dark:text-primary-300 tabular-nums">
              {{ formatMoney(line.unitPrice * line.quantity, 'EGP') }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="cartLocked" class="rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-950/20 px-3 py-2 text-sm text-amber-900 dark:text-amber-200">
        🔒 {{ t('backoffice.pos.cartLockedNotice', { number: pendingOrderNumber }) }}
      </div>

      <AppTextarea
        :model-value="note"
        :label="noteLabel"
        :rows="2"
        :disabled="cartLocked"
        :placeholder="t('backoffice.pos.cart.notePlaceholder')"
        @update:model-value="emit('update:note', $event)"
      />
    </div>

    <div class="border-t border-stone-200 dark:border-border p-3 space-y-3 flex-shrink-0 bg-white dark:bg-surface">
      <div class="space-y-1.5">
        <div class="flex items-center justify-between gap-3 text-sm text-gray-500 dark:text-gray-400">
          <span>{{ serverSummary ? t('backoffice.pos.cart.serverTotal') : t('backoffice.pos.cart.itemsSubtotal') }}</span>
          <span class="tabular-nums">{{ formatMoney(displayedTotal, 'EGP') }}</span>
        </div>
        <div v-if="serverSummary && Number(serverSummary.discount_amount) > 0" class="flex items-center justify-between gap-3 text-sm text-success">
          <span>{{ t('backoffice.pos.cart.discount') }}</span>
          <span class="tabular-nums">−{{ formatMoney(serverSummary.discount_amount, 'EGP') }}</span>
        </div>
        <div class="flex items-end justify-between gap-3 pt-2 border-t border-stone-100 dark:border-border">
          <span class="font-black text-gray-900 dark:text-gray-100">
            {{ serverSummary ? t('backoffice.pos.total') : t('backoffice.pos.cart.estimatedTotal') }}
          </span>
          <span class="text-2xl font-black text-primary-800 dark:text-primary-300 tabular-nums">{{ formatMoney(displayedTotal, 'EGP') }}</span>
        </div>
      </div>

      <AppButton
        variant="outline"
        size="sm"
        block
        :disabled="cart.length === 0"
        :loading="applyingDiscount"
        @click="emit('discount')"
      >
        🏷️ {{ t('backoffice.pos.applyDiscount') }}
      </AppButton>
      <p v-if="discountError" role="alert" class="text-xs text-danger">{{ discountError }}</p>

      <div class="grid grid-cols-2 gap-2">
        <AppButton
          :variant="payPrimary ? 'outline' : 'primary'"
          size="lg"
          :disabled="cart.length === 0"
          :loading="submitting"
          @click="emit('send')"
        >
          🍳 {{ t('backoffice.pos.sendToKitchen') }}
        </AppButton>
        <AppButton
          :variant="payPrimary ? 'primary' : 'outline'"
          size="lg"
          :disabled="cart.length === 0 || !online"
          :loading="submitting"
          @click="emit('pay')"
        >
          💳 {{ t('backoffice.pos.cart.payNow') }}
        </AppButton>
      </div>
      <p v-if="!online" class="text-xs text-amber-700 dark:text-amber-300 text-center">
        {{ t('backoffice.pos.cart.paymentOffline') }}
      </p>
    </div>
  </aside>
</template>

<script setup lang="ts">
// برنامج ولاء العملاء (C-01) — استُخرج من CRMView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, parseApiTimestamp, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface LoyaltyProgram {
  id: number; branch_id: number; points_per_egp: number
  redeem_rate: number; min_redeem_points: number; is_active: boolean
}
interface LoyaltyAccount {
  id: number; customer_id: number; balance: number; lifetime_earned: number; lifetime_redeemed: number
}
interface LoyaltyTransaction {
  id: number; points: number; transaction_type: string; reference: string | null; created_at: string
}
interface LoyaltyRedeemForm { customer_id: string; points: string; reference: string }

const { t } = useI18n()
const { formatDate: fmtDateFn } = useStaffFormat()
const toast = useToast()
const authStore = useAuthStore()
const branchId = computed(() => props.branchId)

function fmtDate(d?: string | null) {
  if (!d) return '—'
  try { return fmtDateFn(parseApiTimestamp(d)) } catch { return d }
}

const loyaltyProgram = ref<LoyaltyProgram | null>(null)
const loyaltyLoading = ref(false)
const loyaltyCustomerId = ref('')
const loyaltyAccount = ref<LoyaltyAccount | null>(null)
const loyaltyTransactions = ref<LoyaltyTransaction[]>([])
const loyaltyAccountLoading = ref(false)
const redeemForm = ref<LoyaltyRedeemForm>({ customer_id: '', points: '', reference: '' })
const redeemLoading = ref(false)
const showLoyaltySetup = ref(false)
const loyaltySetupForm = ref({ points_per_egp: '1', redeem_rate: '0.5', min_redeem_points: '100', is_active: true })

async function loadLoyaltyProgram() {
  loyaltyLoading.value = true
  try {
    const res = await api.get(ENDPOINTS.crm.loyaltyProgram, { params: { branch_id: branchId.value } })
    loyaltyProgram.value = res.data
  } catch { loyaltyProgram.value = null }
  finally { loyaltyLoading.value = false }
}

async function saveLoyaltyProgram() {
  try {
    const payload = {
      branch_id: branchId.value,
      points_per_egp: parseFloat(loyaltySetupForm.value.points_per_egp),
      redeem_rate: parseFloat(loyaltySetupForm.value.redeem_rate),
      min_redeem_points: parseInt(loyaltySetupForm.value.min_redeem_points),
      is_active: loyaltySetupForm.value.is_active,
    }
    if (loyaltyProgram.value) {
      const res = await api.patch(ENDPOINTS.crm.loyaltyProgram, payload, { params: { branch_id: branchId.value } })
      loyaltyProgram.value = res.data
    } else {
      const res = await api.post(ENDPOINTS.crm.loyaltyProgram, payload)
      loyaltyProgram.value = res.data
    }
    showLoyaltySetup.value = false
    toast.success(t('backoffice.crm.msg.loyaltySettingsSaved'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.saveFailed'))
  }
}

async function lookupLoyaltyAccount() {
  const id = parseInt(loyaltyCustomerId.value)
  if (!id) return
  loyaltyAccountLoading.value = true
  try {
    const [accRes, txRes] = await Promise.all([
      api.get(ENDPOINTS.crm.loyaltyAccount, { params: { branch_id: branchId.value, customer_id: id } }),
      api.get(ENDPOINTS.crm.loyaltyTransactions, { params: { branch_id: branchId.value, customer_id: id, limit: 20 } }),
    ])
    loyaltyAccount.value = accRes.data
    loyaltyTransactions.value = txRes.data ?? []
  } catch { toast.error(t('backoffice.crm.msg.loyaltyAccountNotFound')) }
  finally { loyaltyAccountLoading.value = false }
}

async function redeemPoints() {
  redeemLoading.value = true
  try {
    await api.post(ENDPOINTS.crm.loyaltyRedeem, {
      branch_id: branchId.value,
      customer_id: parseInt(redeemForm.value.customer_id),
      points: parseInt(redeemForm.value.points),
      reference: redeemForm.value.reference || null,
    })
    toast.success(t('backoffice.crm.msg.pointsRedeemed'))
    redeemForm.value = { customer_id: '', points: '', reference: '' }
    if (loyaltyAccount.value) await lookupLoyaltyAccount()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.redeemPointsError'))
  } finally { redeemLoading.value = false }
}

onMounted(loadLoyaltyProgram)
</script>

<template>
  <div class="space-y-5">
    <!-- إعدادات البرنامج -->
    <AppCard :title="t('backoffice.crm.loyaltyProgramTitle')">
      <div v-if="loyaltyLoading" class="flex justify-center py-6"><AppSpinner /></div>
      <div v-else-if="loyaltyProgram" class="space-y-3">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.crm.pointPer') }}</div>
            <div class="text-xl font-black text-gray-800 dark:text-gray-200">{{ loyaltyProgram.points_per_egp }} {{ t('backoffice.crm.egp') }}</div>
          </div>
          <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.crm.pointValue') }}</div>
            <div class="text-xl font-black text-gray-800 dark:text-gray-200">{{ loyaltyProgram.redeem_rate }} {{ t('backoffice.crm.egp') }}</div>
          </div>
          <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.crm.minRedeem') }}</div>
            <div class="text-xl font-black text-gray-800 dark:text-gray-200">{{ loyaltyProgram.min_redeem_points }}</div>
          </div>
          <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.crm.statusLabel') }}</div>
            <AppBadge :variant="loyaltyProgram.is_active ? 'success' : 'neutral'">
              {{ loyaltyProgram.is_active ? t('backoffice.crm.programActive') : t('backoffice.crm.programSuspended') }}
            </AppBadge>
          </div>
        </div>
        <AppButton v-if="authStore.roleLevel >= 80" size="sm" variant="outline" @click="showLoyaltySetup = !showLoyaltySetup">
          ✏️ {{ t('backoffice.crm.editSettings') }}
        </AppButton>
      </div>
      <EmptyState v-else icon="🎁" :title="t('backoffice.crm.noLoyaltyProgram')" :subtitle="t('backoffice.crm.noLoyaltyProgramHint')">
        <AppButton size="sm" @click="showLoyaltySetup = true">{{ t('backoffice.crm.createProgram') }}</AppButton>
      </EmptyState>

      <!-- فورم الإعدادات -->
      <div v-if="showLoyaltySetup" class="mt-4 border-t border-stone-200 dark:border-border pt-4 space-y-3">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <label class="text-xs font-semibold text-gray-600 dark:text-gray-400 block mb-1">{{ t('backoffice.crm.pointPerEgp') }}</label>
            <input v-model="loyaltySetupForm.points_per_egp" type="number" min="0.01" step="0.01"
              class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="text-xs font-semibold text-gray-600 dark:text-gray-400 block mb-1">{{ t('backoffice.crm.pointValueEgp') }}</label>
            <input v-model="loyaltySetupForm.redeem_rate" type="number" min="0.01" step="0.01"
              class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="text-xs font-semibold text-gray-600 dark:text-gray-400 block mb-1">{{ t('backoffice.crm.minRedeem') }}</label>
            <input v-model="loyaltySetupForm.min_redeem_points" type="number" min="1"
              class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div class="flex flex-col justify-end">
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input v-model="loyaltySetupForm.is_active" type="checkbox" class="rounded" />
              {{ t('backoffice.crm.activateProgram') }}
            </label>
          </div>
        </div>
        <div class="flex gap-2">
          <AppButton size="sm" @click="saveLoyaltyProgram">{{ t('backoffice.crm.save') }}</AppButton>
          <AppButton size="sm" variant="ghost" @click="showLoyaltySetup = false">{{ t('backoffice.crm.cancel') }}</AppButton>
        </div>
      </div>
    </AppCard>

    <!-- بحث عن عميل -->
    <AppCard :title="t('backoffice.crm.customerPoints')">
      <div class="flex gap-2 mb-4">
        <input v-model="loyaltyCustomerId" type="number" :placeholder="t('backoffice.crm.customerIdNumber')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-40"
          @keyup.enter="lookupLoyaltyAccount" />
        <AppButton size="sm" :loading="loyaltyAccountLoading" @click="lookupLoyaltyAccount">{{ t('backoffice.crm.search') }}</AppButton>
      </div>

      <div v-if="loyaltyAccount" class="space-y-4">
        <!-- ملخص الرصيد -->
        <div class="grid grid-cols-3 gap-3 text-center">
          <div class="rounded-xl bg-green-50 p-3 dark:bg-green-950/40">
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.crm.currentBalance') }}</div>
            <div class="text-2xl font-black text-green-700 dark:text-green-300">{{ loyaltyAccount.balance }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.crm.point') }}</div>
          </div>
          <div class="rounded-xl bg-blue-50 p-3 dark:bg-blue-950/40">
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.crm.lifetimeEarned') }}</div>
            <div class="text-xl font-black text-blue-700 dark:text-blue-300">{{ loyaltyAccount.lifetime_earned }}</div>
          </div>
          <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.crm.lifetimeRedeemed') }}</div>
            <div class="text-xl font-black text-gray-700 dark:text-gray-300">{{ loyaltyAccount.lifetime_redeemed }}</div>
          </div>
        </div>

        <!-- فورم الاسترداد -->
        <div class="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
          <div class="text-sm font-bold text-amber-800 dark:text-amber-300">🎁 {{ t('backoffice.crm.redeemPoints') }}</div>
          <div class="flex gap-2 flex-wrap">
            <input v-model="redeemForm.customer_id" type="number" :placeholder="t('backoffice.crm.customerIdShort')"
              :value="loyaltyCustomerId"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-32" />
            <input v-model="redeemForm.points" type="number" min="1" :placeholder="t('backoffice.crm.pointsCount')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-32" />
            <input v-model="redeemForm.reference" type="text" :placeholder="t('backoffice.crm.referenceOptional')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm flex-1 min-w-[120px]" />
            <AppButton size="sm" variant="primary" :loading="redeemLoading" @click="redeemPoints">{{ t('backoffice.crm.redeem') }}</AppButton>
          </div>
          <div v-if="loyaltyProgram" class="text-xs text-amber-700 dark:text-amber-300">
            {{ t('backoffice.crm.redeemValueLine', { value: redeemForm.points ? (parseFloat(redeemForm.points) * loyaltyProgram.redeem_rate).toFixed(2) : '0', min: loyaltyProgram.min_redeem_points }) }}
          </div>
        </div>

        <!-- سجل المعاملات -->
        <div>
          <div class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">{{ t('backoffice.crm.recentTransactions') }}</div>
          <div v-if="loyaltyTransactions.length === 0" class="text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.crm.noTransactions') }}</div>
          <div v-for="tx in loyaltyTransactions" :key="tx.id"
            class="flex items-center justify-between py-2 border-b border-stone-100 dark:border-border/50 last:border-0 text-sm">
            <div>
              <span :class="tx.points > 0 ? 'font-bold text-green-600 dark:text-green-300' : 'font-bold text-red-600 dark:text-red-300'">
                {{ tx.points > 0 ? '+' : '' }}{{ tx.points }} {{ t('backoffice.crm.point') }}
              </span>
              <span class="text-gray-500 dark:text-gray-400 ms-2 text-xs">{{ tx.transaction_type }}</span>
              <span v-if="tx.reference" class="text-gray-400 dark:text-gray-400 ms-1 text-xs">· {{ tx.reference }}</span>
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-400">{{ fmtDate(tx.created_at) }}</div>
          </div>
        </div>
      </div>

      <EmptyState v-else-if="!loyaltyAccountLoading" icon="🔍" :title="t('backoffice.crm.searchByCustomerId')" />
    </AppCard>
  </div>
</template>

<script setup lang="ts">
// قنوات التحصيل (صندوق/Visa CIB/Vodafone Cash...) — استُخرج من
// FinanceView.vue (تقسيم الملفات الكبيرة، 2026-09-07). كل قناة مربوطة
// إجباريًا بحساب GL وباختيار حساب بنكي. الصلاحية الحقيقية على الـbackend
// (get_finance_user + assert_branch_access)، الشاشة دي مجرد واجهة —
// مفيش أي منطق تحقق بيزنس هنا (راجع CLAUDE.md §4). accounts/bankAccounts
// نسخ محلية مستقلة (نفس نمط تكرار الجلب المتبع في باقي التابات
// المُستخرجة) — مفيش تزامن مباشر مطلوب مع تابات المصروفات/العهدة/إذن
// القبض اللي لسه بتستخدم نسخها الخاصة جوه FinanceView.vue.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { AppButton, AppCard, AppBadge, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface BankAccount {
  id: number; bank_name: string; account_name: string; account_number: string
  currency: string; opening_balance: number; is_active: boolean
}
interface PaymentChannel {
  id: number; branch_id: number; code: string; name: string; name_ar: string | null
  method: 'cash' | 'card' | 'wallet'
  gl_account_id: number; gl_account_code: string; gl_account_name: string
  bank_account_id: number | null; bank_account_name: string | null
  is_default: boolean; is_active: boolean; sort_order: number
}

const toast = useToast()
const { t } = useI18n()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const accounts = ref<Account[]>([])
const bankAccounts = ref<BankAccount[]>([])
const paymentChannels = ref<PaymentChannel[]>([])
const showChannelForm = ref(false)
const editingChannelId = ref<number | null>(null)
const channelFormError = ref('')
const channelSaving = ref(false)
const channelForm = ref({
  code: '', name: '', name_ar: '', method: 'cash' as 'cash' | 'card' | 'wallet',
  gl_account_id: null as number | null, bank_account_id: null as number | null,
  is_default: false,
})

const glAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'asset'))

function resetChannelForm() {
  editingChannelId.value = null
  channelFormError.value = ''
  channelForm.value = { code: '', name: '', name_ar: '', method: 'cash', gl_account_id: null, bank_account_id: null, is_default: false }
}

async function loadPaymentChannels() {
  loading.value = true
  try {
    const [channelsRes] = await Promise.all([
      api.get(ENDPOINTS.finance.paymentChannels, { params: { branch_id: branchId.value } }),
      accounts.value.length ? Promise.resolve() : api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } }).then(r => { accounts.value = r.data.accounts ?? r.data.items ?? r.data }),
      bankAccounts.value.length ? Promise.resolve() : api.get(ENDPOINTS.finance.bankAccounts, { params: { branch_id: branchId.value } }).then(r => { bankAccounts.value = r.data }),
    ])
    paymentChannels.value = channelsRes.data
  } catch { toast.error(t('backoffice.finance.paymentChannels.loadError')) }
  finally { loading.value = false }
}

function editChannel(channel: PaymentChannel) {
  editingChannelId.value = channel.id
  channelFormError.value = ''
  channelForm.value = {
    code: channel.code, name: channel.name, name_ar: channel.name_ar ?? '',
    method: channel.method, gl_account_id: channel.gl_account_id,
    bank_account_id: channel.bank_account_id, is_default: channel.is_default,
  }
  showChannelForm.value = true
}

async function savePaymentChannel() {
  if (!channelForm.value.code || !channelForm.value.name || !channelForm.value.gl_account_id) {
    channelFormError.value = t('backoffice.finance.paymentChannels.fieldsRequired'); return
  }
  channelSaving.value = true
  channelFormError.value = ''
  try {
    if (editingChannelId.value) {
      await api.patch(ENDPOINTS.finance.paymentChannel(editingChannelId.value), {
        name: channelForm.value.name,
        name_ar: channelForm.value.name_ar || null,
        gl_account_id: channelForm.value.gl_account_id,
        bank_account_id: channelForm.value.bank_account_id,
        clear_bank_account: channelForm.value.bank_account_id == null,
        is_default: channelForm.value.is_default,
      })
      toast.success(t('backoffice.finance.paymentChannels.updated'))
    } else {
      await api.post(ENDPOINTS.finance.paymentChannels, {
        branch_id: branchId.value,
        code: channelForm.value.code,
        name: channelForm.value.name,
        name_ar: channelForm.value.name_ar || null,
        method: channelForm.value.method,
        gl_account_id: channelForm.value.gl_account_id,
        bank_account_id: channelForm.value.bank_account_id,
        is_default: channelForm.value.is_default,
      })
      toast.success(t('backoffice.finance.paymentChannels.created'))
    }
    showChannelForm.value = false
    resetChannelForm()
    await loadPaymentChannels()
  } catch (e: unknown) {
    channelFormError.value = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.paymentChannels.saveError')
  } finally {
    channelSaving.value = false
  }
}

async function toggleChannelActive(channel: PaymentChannel) {
  try {
    await api.patch(ENDPOINTS.finance.paymentChannel(channel.id), { is_active: !channel.is_active })
    toast.success(channel.is_active ? t('backoffice.finance.paymentChannels.disabled') : t('backoffice.finance.paymentChannels.enabled'))
    await loadPaymentChannels()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.paymentChannels.saveError'))
  }
}

async function setChannelDefault(channel: PaymentChannel) {
  if (channel.is_default) return
  try {
    await api.patch(ENDPOINTS.finance.paymentChannel(channel.id), { is_default: true })
    toast.success(t('backoffice.finance.paymentChannels.defaultSet'))
    await loadPaymentChannels()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.paymentChannels.saveError'))
  }
}

const paymentChannelMethodLabels = computed<Record<string, string>>(() => ({
  cash: t('backoffice.finance.methodCash'),
  card: t('backoffice.finance.methodCard'),
  wallet: t('backoffice.finance.paymentChannels.methodWallet'),
}))

onMounted(loadPaymentChannels)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <p class="text-sm text-gray-500 dark:text-gray-400 max-w-2xl">{{ t('backoffice.finance.paymentChannels.description') }}</p>
      <AppButton size="sm" @click="() => { resetChannelForm(); showChannelForm = true }">
        {{ t('backoffice.finance.paymentChannels.new') }}
      </AppButton>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[760px]">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.name') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.method') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.glAccount') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.bankAccount') }}</th>
              <th class="px-4 py-3 text-center text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.default') }}</th>
              <th class="px-4 py-3 text-center text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.status') }}</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ch in paymentChannels" :key="ch.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3">
                <div class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ ch.name_ar || ch.name }}</div>
                <div class="text-xs text-gray-400 dark:text-gray-400 font-mono">{{ ch.code }}</div>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ paymentChannelMethodLabels[ch.method] }}</td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                <span class="font-mono">{{ ch.gl_account_code }}</span> — {{ ch.gl_account_name }}
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ ch.bank_account_name ?? '—' }}</td>
              <td class="px-4 py-3 text-center">
                <button v-if="!ch.is_default" @click="setChannelDefault(ch)"
                  class="text-xs text-blue-600 dark:text-blue-300 hover:underline">
                  {{ t('backoffice.finance.paymentChannels.setDefault') }}
                </button>
                <AppBadge v-else variant="success" size="sm">{{ t('backoffice.finance.paymentChannels.default') }}</AppBadge>
              </td>
              <td class="px-4 py-3 text-center">
                <AppBadge :variant="ch.is_active ? 'success' : 'neutral'" size="sm">
                  {{ ch.is_active ? t('backoffice.finance.paymentChannels.active') : t('backoffice.finance.paymentChannels.inactive') }}
                </AppBadge>
              </td>
              <td class="px-4 py-3 text-end whitespace-nowrap">
                <button @click="editChannel(ch)" class="text-xs text-blue-600 dark:text-blue-300 hover:underline me-3">
                  {{ t('backoffice.finance.paymentChannels.edit') }}
                </button>
                <button @click="toggleChannelActive(ch)" class="text-xs hover:underline"
                  :class="ch.is_active ? 'text-red-600 dark:text-red-300' : 'text-emerald-600 dark:text-emerald-300'">
                  {{ ch.is_active ? t('backoffice.finance.paymentChannels.disable') : t('backoffice.finance.paymentChannels.enable') }}
                </button>
              </td>
            </tr>
            <tr v-if="paymentChannels.length === 0">
              <td colspan="7" class="px-4 py-8">
                <EmptyState icon="💳" :title="t('backoffice.finance.paymentChannels.empty')" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <AppModal :open="showChannelForm"
      :title="editingChannelId ? t('backoffice.finance.paymentChannels.editTitle') : t('backoffice.finance.paymentChannels.newTitle')"
      size="md" @close="showChannelForm = false">
      <div class="space-y-3">
        <p v-if="channelFormError" class="text-sm text-red-600 dark:text-red-300 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">{{ channelFormError }}</p>

        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.code') }}</label>
          <input v-model="channelForm.code" :disabled="!!editingChannelId"
            class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface disabled:opacity-50" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.nameEn') }}</label>
            <input v-model="channelForm.name" class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.nameAr') }}</label>
            <input v-model="channelForm.name_ar" class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface" />
          </div>
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.method') }}</label>
          <select v-model="channelForm.method" :disabled="!!editingChannelId"
            class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface disabled:opacity-50">
            <option value="cash">{{ t('backoffice.finance.methodCash') }}</option>
            <option value="card">{{ t('backoffice.finance.methodCard') }}</option>
            <option value="wallet">{{ t('backoffice.finance.paymentChannels.methodWallet') }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.glAccount') }}</label>
          <select v-model.number="channelForm.gl_account_id"
            class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface">
            <option :value="null">{{ t('backoffice.finance.paymentChannels.selectAccount') }}</option>
            <option v-for="acc in glAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
          </select>
        </div>
        <div v-if="channelForm.method !== 'cash'">
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.bankAccount') }}</label>
          <select v-model.number="channelForm.bank_account_id"
            class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface">
            <option :value="null">{{ t('backoffice.finance.paymentChannels.noBankAccount') }}</option>
            <option v-for="ba in bankAccounts" :key="ba.id" :value="ba.id">{{ ba.bank_name }} — {{ ba.account_name }}</option>
          </select>
        </div>
        <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <input type="checkbox" v-model="channelForm.is_default" />
          {{ t('backoffice.finance.paymentChannels.setAsDefault') }}
        </label>

        <div class="flex justify-end gap-2 pt-2">
          <AppButton variant="outline" size="sm" @click="showChannelForm = false">{{ t('backoffice.finance.cancel') }}</AppButton>
          <AppButton size="sm" :disabled="channelSaving" @click="savePaymentChannel">
            {{ channelSaving ? t('backoffice.finance.saving') : t('backoffice.finance.save') }}
          </AppButton>
        </div>
      </div>
    </AppModal>
  </div>
</template>

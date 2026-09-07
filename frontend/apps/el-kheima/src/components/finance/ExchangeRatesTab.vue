<script setup lang="ts">
// POS-03: أسعار الصرف — استُخرج من FinanceView.vue (تقسيم الملفات الكبيرة،
// 2026-09-07، أول تجربة آمنة على الفرونت إند). تاب معزول بالكامل (state
// وfunctions خاصة به بس) — يعيد تحميل البيانات عند التركيب (onMounted)
// بدل ما يعتمد على FinanceView's loadTab dispatcher، عشان يبقى مكوّن قائم
// بذاته من غير حاجة لـtemplate refs أو exposed methods.
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { AppCard, AppButton, EmptyState, useToast } from '@resort-os/ui'

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }

interface ExchangeRateItem {
  id: number
  from_currency: string
  to_currency: string
  rate: string
  effective_date: string
}

const toast = useToast()
const { t } = useI18n()

const exchangeRates = ref<ExchangeRateItem[]>([])
const fxLoading = ref(false)
const fxError = ref('')
const fxNewFrom = ref('USD')
const fxNewTo = ref('EGP')
const fxNewRate = ref('')
const fxNewDate = ref(new Date().toISOString().slice(0, 10))
const fxSaving = ref(false)

const SUPPORTED_CURRENCIES = ['USD', 'EUR', 'SAR', 'GBP', 'EGP']

async function loadExchangeRates() {
  fxLoading.value = true
  fxError.value = ''
  try {
    // GET /finance/exchange-rates لا يقبل branch_id (أسعار الصرف عالمية مش
    // مربوطة بفرع) ولا limit (بس size، حد أقصى 200) — كانا بيتجاهَلوا بصمت
    // وبيرجّع الـdefault الحالي (page=1/size=50) دايمًا، اللي طابق الغرض هنا
    // بالصدفة بس لسه drift حقيقي عن الـcontract (OPS-DATA-02 §6.3).
    //
    // ⚠️ باج حقيقي كان هنا (مراجعة Codex 2026-08-30، M-04): المسار كان
    // '/finance/exchange-rates' من غير بادئة '/api/v1' (باقي الاستدعاءات
    // في الملف ده بتستخدم ENDPOINTS.* اللي فيها البادئة دايمًا). axios
    // baseURL فاضي، وnginx بيوجّه /api/ بس للباك إند — فالمسار الناقص كان
    // بيقع في SPA fallback ويرجّع HTML بدل JSON، يعني الشاشة كانت معطّلة
    // تمامًا في الإنتاج رغم نجاح build/type-check.
    const { data } = await api.get(ENDPOINTS.finance.exchangeRates, {
      params: { page: 1, size: 100 },
    })
    exchangeRates.value = data.items ?? data ?? []
  } catch {
    fxError.value = t('backoffice.finance.fx.loadError')
  } finally {
    fxLoading.value = false
  }
}

async function saveExchangeRate() {
  if (!fxNewRate.value || !fxNewDate.value) return
  fxSaving.value = true
  try {
    await api.post(ENDPOINTS.finance.exchangeRates, {
      from_currency: fxNewFrom.value,
      to_currency:   fxNewTo.value,
      rate:          fxNewRate.value,
      effective_date: fxNewDate.value,
    })
    toast.success(t('backoffice.finance.fx.saved'))
    fxNewRate.value = ''
    fxNewDate.value = new Date().toISOString().slice(0, 10)
    await loadExchangeRates()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.fx.saveError'))
  } finally {
    fxSaving.value = false
  }
}

onMounted(loadExchangeRates)
</script>

<template>
  <div class="space-y-6">
    <AppCard>
      <h3 class="text-lg font-black text-gray-900 dark:text-gray-100 mb-4">{{ t('backoffice.finance.fx.addTitle') }}</h3>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 items-end">
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.finance.fx.fromCurrency') }}</label>
          <select v-model="fxNewFrom" class="w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option v-for="cur in SUPPORTED_CURRENCIES.filter(c => c !== 'EGP')" :key="cur" :value="cur">{{ cur }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.finance.fx.toCurrency') }}</label>
          <select v-model="fxNewTo" class="w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option value="EGP">EGP</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.finance.fx.rate') }} (1 {{ fxNewFrom }} = ? EGP)</label>
          <input v-model="fxNewRate" type="number" step="0.01" min="0.01"
            class="w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm font-bold tabular-nums"
            :placeholder="fxNewFrom === 'USD' ? '48.00' : fxNewFrom === 'EUR' ? '52.00' : '0.00'" />
        </div>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.finance.fx.effectiveDate') }}</label>
          <input v-model="fxNewDate" type="date"
            class="w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
        </div>
      </div>
      <div class="mt-4 flex gap-2 items-center">
        <AppButton variant="primary" :loading="fxSaving" :disabled="!fxNewRate || !fxNewDate" @click="saveExchangeRate">
          {{ t('backoffice.finance.fx.save') }}
        </AppButton>
        <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.finance.fx.hint') }}</p>
      </div>
    </AppCard>

    <AppCard>
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.fx.historyTitle') }}</h3>
        <AppButton variant="ghost" size="sm" :loading="fxLoading" @click="loadExchangeRates">{{ t('backoffice.finance.refresh') }}</AppButton>
      </div>
      <p v-if="fxError" role="alert" class="text-sm text-danger">{{ fxError }}</p>
      <EmptyState v-else-if="!fxLoading && exchangeRates.length === 0" icon="💱" :title="t('backoffice.finance.fx.empty')" />
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[600px] text-sm">
          <thead>
            <tr class="text-start text-gray-500 dark:text-gray-400 border-b border-stone-200 dark:border-border">
              <th class="pb-2 font-semibold text-start">{{ t('backoffice.finance.fx.fromCurrency') }}</th>
              <th class="pb-2 font-semibold text-start">{{ t('backoffice.finance.fx.toCurrency') }}</th>
              <th class="pb-2 font-semibold text-end">{{ t('backoffice.finance.fx.rate') }}</th>
              <th class="pb-2 font-semibold text-start">{{ t('backoffice.finance.fx.effectiveDate') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in exchangeRates" :key="r.id" class="border-b border-stone-100 dark:border-border last:border-0">
              <td class="py-2 font-bold">{{ r.from_currency }}</td>
              <td class="py-2">{{ r.to_currency }}</td>
              <td class="py-2 text-end tabular-nums font-bold">{{ Number(r.rate).toFixed(4) }}</td>
              <td class="py-2 text-gray-500 dark:text-gray-400">{{ r.effective_date }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>
  </div>
</template>

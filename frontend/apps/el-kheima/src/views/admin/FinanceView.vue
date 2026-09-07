<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@resort-os/core'
import ExchangeRatesTab from '../../components/finance/ExchangeRatesTab.vue'
import AgingReportTab from '../../components/finance/AgingReportTab.vue'
import CostCentersTab from '../../components/finance/CostCentersTab.vue'
import DepreciationTab from '../../components/finance/DepreciationTab.vue'
import BankReconciliationTab from '../../components/finance/BankReconciliationTab.vue'
import ChecksTab from '../../components/finance/ChecksTab.vue'
import PeriodsTab from '../../components/finance/PeriodsTab.vue'
import OverviewTab from '../../components/finance/OverviewTab.vue'
import AccountsTab from '../../components/finance/AccountsTab.vue'
import PaymentChannelsTab from '../../components/finance/PaymentChannelsTab.vue'
import JournalTab from '../../components/finance/JournalTab.vue'
import ShiftsTab from '../../components/finance/ShiftsTab.vue'
import ExpensesTab from '../../components/finance/ExpensesTab.vue'
import CustodiesTab from '../../components/finance/CustodiesTab.vue'
import CashReceiptsTab from '../../components/finance/CashReceiptsTab.vue'
import BalanceSheetTab from '../../components/finance/BalanceSheetTab.vue'
import TrialBalanceTab from '../../components/finance/TrialBalanceTab.vue'
import IncomeStatementTab from '../../components/finance/IncomeStatementTab.vue'

const { t } = useI18n()
const auth = useAuthStore()
// CX-02C: branchId comes from bootstrap (session-scoped, no ?? 1 fallback).
// activeBranchId is null when requires_branch_selection=true — in that case
// API calls carry no branch_id and the server returns 409 BRANCH_CONTEXT_REQUIRED.
const branchId = computed(() => auth.activeBranchId)
const tab = ref<'overview' | 'checks' | 'accounts' | 'cost-centers' | 'balance-sheet' | 'depreciation' | 'bank-reconciliation' | 'shifts' | 'exchange-rates' | 'journal' | 'payment-channels' | 'expenses' | 'custodies' | 'cash-receipts' | 'trial-balance' | 'income-statement' | 'aging' | 'periods'>('overview')
const activeGroupIdx = ref(0)

// كل تاب استُخرج لكومبوننت خاص بيه (تقسيم الملفات الكبيرة، 2026-09-07) —
// الملف ده بقى façade بس بيحدّد التاب النشط ويمرر branchId.
async function loadTab(tabId: typeof tab.value) {
  tab.value = tabId
  if (tabId === 'shifts') { return }
  if (tabId === 'depreciation') { return }
  if (tabId === 'bank-reconciliation') { return }
  if (tabId === 'balance-sheet') { return }
  if (tabId === 'cost-centers') { return }
  if (tabId === 'journal') { return }
  if (tabId === 'payment-channels') { return }
  if (tabId === 'expenses') { return }
  if (tabId === 'custodies') { return }
  if (tabId === 'cash-receipts') { return }
  if (tabId === 'checks') { return }
  if (tabId === 'trial-balance') { return }
  if (tabId === 'income-statement') { return }
  if (tabId === 'periods') { return }
  if (tabId === 'overview') { return }
  if (tabId === 'accounts') { return }
}

onMounted(() => loadTab('overview'))

// تنظيم شاشة المالية (2026-08-19، طلب Mohamed — "متنظمة ومتهيأة للمحاسب
// يقدر يشتغل ببرنامج محاسبي حقيقي") — قايمة مسطّحة من 17 تبويب بقت 4
// مجموعات منطقية زي أي برنامج محاسبة حقيقي: التشغيل اليومي (فيها الورديات
// اللي المحاسب بيراقب بيها الكاشير)، الحسابات والقيود، التقارير المالية،
// الإعدادات المتقدمة.
const tabGroups = computed<{ label: string; tabs: { val: typeof tab.value; label: string }[] }[]>(() => [
  {
    label: t('backoffice.finance.groups.daily'),
    tabs: [
      { val: 'overview',         label: t('backoffice.finance.tabs.overview') },
      { val: 'shifts',           label: t('backoffice.finance.tabs.shifts') },
      { val: 'expenses',         label: t('backoffice.finance.tabs.expenses') },
      { val: 'custodies',        label: t('backoffice.finance.tabs.custodies') },
      { val: 'cash-receipts',    label: t('backoffice.finance.tabs.cashReceipts') },
      { val: 'payment-channels', label: t('backoffice.finance.tabs.paymentChannels') },
    ],
  },
  {
    label: t('backoffice.finance.groups.ledger'),
    tabs: [
      { val: 'accounts',      label: t('backoffice.finance.tabs.accounts') },
      { val: 'journal',       label: t('backoffice.finance.tabs.journal') },
      { val: 'cost-centers',  label: t('backoffice.finance.tabs.costCenters') },
      { val: 'checks',        label: t('backoffice.finance.tabs.checks') },
    ],
  },
  {
    label: t('backoffice.finance.groups.reports'),
    tabs: [
      { val: 'trial-balance',    label: t('backoffice.finance.tabs.trialBalance') },
      { val: 'income-statement', label: t('backoffice.finance.tabs.incomeStatement') },
      { val: 'balance-sheet',    label: t('backoffice.finance.tabs.balanceSheet') },
      { val: 'aging',            label: t('backoffice.finance.tabs.aging') },
    ],
  },
  {
    label: t('backoffice.finance.groups.advanced'),
    tabs: [
      { val: 'periods',             label: t('backoffice.finance.tabs.periods') },
      { val: 'exchange-rates',      label: t('backoffice.finance.tabs.exchangeRates') },
      { val: 'depreciation',        label: t('backoffice.finance.tabs.depreciation') },
      { val: 'bank-reconciliation', label: t('backoffice.finance.tabs.bankReconciliation') },
    ],
  },
])

</script>

<template>
  <div>
    <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100 mb-6">{{ t('backoffice.finance.title') }}</h2>

    <!-- مجموعات رئيسية (2026-08-19) — بديل صف الـ17 تبويب القديم المتناثر،
         نفس أسلوب أي برنامج محاسبة حقيقي (تشغيل يومي / حسابات / تقارير /
         إعدادات متقدمة). -->
    <div class="flex gap-1 bg-stone-50 dark:bg-gray-800/40 p-1 rounded-xl mb-2 w-fit flex-wrap border border-stone-200 dark:border-border/50">
      <button v-for="(group, idx) in tabGroups" :key="group.label"
        @click="activeGroupIdx = idx"
        :class="['px-3 py-1.5 rounded-lg text-xs font-bold transition-all', activeGroupIdx === idx ? 'bg-primary-700 text-white shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300']"
      >{{ group.label }}</button>
    </div>

    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl mb-6 w-fit flex-wrap">
      <button v-for="tabDef in tabGroups[activeGroupIdx].tabs"
        :key="tabDef.val" @click="loadTab(tabDef.val)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === tabDef.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300']"
      >{{ tabDef.label }}</button>
    </div>

    <!-- Overview -->
    <OverviewTab v-if="tab === 'overview'" :branch-id="branchId" />

    <!-- Checks -->
    <ChecksTab v-if="tab === 'checks'" :branch-id="branchId" />

    <!-- Accounts -->
    <AccountsTab v-if="tab === 'accounts'" :branch-id="branchId" />

    <!-- Cost Centers -->
    <CostCentersTab v-if="tab === 'cost-centers'" :branch-id="branchId" />

    <!-- Balance Sheet (الميزانية العمومية) -->
    <BalanceSheetTab v-if="tab === 'balance-sheet'" :branch-id="branchId" />

    <!-- Trial Balance -->
    <TrialBalanceTab v-if="tab === 'trial-balance'" :branch-id="branchId" />

    <!-- Income Statement -->
    <IncomeStatementTab v-if="tab === 'income-statement'" :branch-id="branchId" />

    <!-- Aging Report -->
    <AgingReportTab v-if="tab === 'aging'" :branch-id="branchId" />

    <!-- Periods (إقفال شهري + سنوي) -->
    <PeriodsTab v-if="tab === 'periods'" :branch-id="branchId" />

    <!-- Depreciation -->
    <DepreciationTab v-if="tab === 'depreciation'" :branch-id="branchId" />

    <!-- Bank Reconciliation -->
    <BankReconciliationTab v-if="tab === 'bank-reconciliation'" :branch-id="branchId" />

    <!-- Shifts tab -->
    <ShiftsTab v-if="tab === 'shifts'" :branch-id="branchId" />

    <!-- POS-03: شاشة إدارة أسعار الصرف — manager+ فقط -->
    <ExchangeRatesTab v-if="tab === 'exchange-rates'" />

    <!-- دفتر اليومية -->
    <JournalTab v-if="tab === 'journal'" :branch-id="branchId" />

    <!-- Payment Channels -->
    <PaymentChannelsTab v-if="tab === 'payment-channels'" :branch-id="branchId" />

    <!-- Expenses (2026-08-16) -->
    <ExpensesTab v-if="tab === 'expenses'" :branch-id="branchId" />

    <!-- Custodies / العهدة (2026-08-19) -->
    <CustodiesTab v-if="tab === 'custodies'" :branch-id="branchId" />

    <!-- Cash Receipts / إذن قبض عام (2026-08-19) -->
    <CashReceiptsTab v-if="tab === 'cash-receipts'" :branch-id="branchId" />

  </div>
</template>

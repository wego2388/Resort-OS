<script setup lang="ts">
// شاشة الملكية الجزئية — واجهة (façade) بسيطة: تابات + إعادة تحميل + عدّادات
// شارات صغيرة مستقلة، وكل تاب مكوّن قائم بذاته تحت components/timeshare/.
// استُخرجت من TimeshareView.vue الأصلي (2129 سطر) بنفس نمط تقسيم
// FinanceView.vue/CRMView.vue/HRView.vue (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { AppButton, AppIcon } from '@resort-os/ui'

import DashboardTab from '../../components/timeshare/DashboardTab.vue'
import CalendarTab from '../../components/timeshare/CalendarTab.vue'
import ClientsTab from '../../components/timeshare/ClientsTab.vue'
import InstallmentsTab from '../../components/timeshare/InstallmentsTab.vue'
import MaintenanceTab from '../../components/timeshare/MaintenanceTab.vue'
import RequestsTab from '../../components/timeshare/RequestsTab.vue'
import SupportTab from '../../components/timeshare/SupportTab.vue'
import WaitlistTab from '../../components/timeshare/WaitlistTab.vue'
import StaffTab from '../../components/timeshare/StaffTab.vue'
import UnitsTab from '../../components/timeshare/UnitsTab.vue'

const { t } = useI18n()
const auth = useAuthStore()
const branchId = computed(() => auth.branchId)

// ── عدّادات الشارات فقط (طلبات الزيارة/تذاكر الدعم المفتوحة) — نسخة خفيفة
// مستقلة عن DashboardTab.vue (اللي بيحمّل ملخص كامل)، عشان الرقم يظهر فورًا
// فوق التابات من غير ما نضطر نحمّل تاب الداشبورد بالكامل مقدمًا.
const badgeCounts = ref({ pending_visit_requests: 0, open_support_tickets: 0 })
async function loadBadgeCounts() {
  try {
    const r = await api.get('/api/v1/timeshare/cs-summary', { params: { branch_id: branchId.value } })
    badgeCounts.value = {
      pending_visit_requests: r.data?.pending_visit_requests || 0,
      open_support_tickets: r.data?.open_support_tickets || 0,
    }
  } catch { /* شارات ثانوية — فشل صامت، DashboardTab.vue بيعرض الملخص الكامل مع رسالة خطأ حقيقية لو فتح */ }
}

const TABS = computed(() => [
  { id: 'dashboard', icon: '🏠', label: t('backoffice.timeshare.tabs.dashboard') },
  { id: 'calendar', icon: '📅', label: t('backoffice.timeshare.tabs.calendar') },
  { id: 'clients', icon: '👤', label: t('backoffice.timeshare.tabs.clients') },
  { id: 'installments', icon: '💰', label: t('backoffice.timeshare.tabs.installments') },
  { id: 'maintenance', icon: '🛠️', label: t('backoffice.timeshare.tabs.maintenance') },
  { id: 'requests', icon: '📝', label: t('backoffice.timeshare.tabs.requests'), badge: badgeCounts.value.pending_visit_requests },
  { id: 'support', icon: '💬', label: t('backoffice.timeshare.tabs.support'), badge: badgeCounts.value.open_support_tickets },
  { id: 'waitlist', icon: '⏳', label: t('backoffice.timeshare.tabs.waitlist') },
  ...(auth.hasRole('timeshare_admin') ? [
    { id: 'staff', icon: '🧑‍💼', label: t('backoffice.timeshare.tabs.staff') },
    { id: 'units', icon: '🏘️', label: t('backoffice.timeshare.tabs.units') },
  ] : []),
])
const activeTab = ref('dashboard')

// ── إعادة تحميل التاب الحالي — كل تاب بيحمّل بياناته لوحده في onMounted،
// فمفيش دالة "تحميل شامل" واحدة بعد التقسيم؛ زرار "تحديث" العام بيغيّر
// المفتاح فيجبر Vue يعيد إنشاء (remount) مكوّن التاب النشط فيعيد تحميله.
const refreshKey = ref(0)
function refreshCurrentTab() {
  refreshKey.value += 1
  loadBadgeCounts()
}

onMounted(loadBadgeCounts)
</script>

<template>
  <div class="space-y-5 pb-6">
    <div class="flex items-start justify-between flex-wrap gap-4">
      <div>
        <h2 class="text-2xl font-black text-gray-950 dark:text-gray-100">{{ t('backoffice.timeshare.title') }}</h2>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.timeshare.workspaceHint') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <AppButton variant="outline" @click="refreshCurrentTab">
          <AppIcon name="refresh" size="sm" /> {{ t('backoffice.timeshare.refresh') }}
        </AppButton>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 dark:bg-gray-800 p-1.5 rounded-2xl overflow-x-auto" role="tablist" :aria-label="t('backoffice.timeshare.tabsLabel')">
      <button v-for="tab in TABS" :key="tab.id" @click="activeTab = tab.id"
        type="button" role="tab" :aria-selected="activeTab === tab.id"
        :class="['min-h-[44px] px-4 py-2 rounded-xl text-sm font-bold whitespace-nowrap transition-all', activeTab === tab.id ? 'bg-white dark:bg-surface shadow-sm text-gray-950 dark:text-gray-100' : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white']">
        {{ tab.icon }} {{ tab.label }}
        <span v-if="('badge' in tab) && (tab.badge ?? 0) > 0"
          class="ms-1.5 inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-black leading-none text-white">
          {{ tab.badge }}
        </span>
      </button>
    </div>

    <DashboardTab v-if="activeTab === 'dashboard'" :key="`dashboard-${refreshKey}`" :branch-id="branchId" />
    <CalendarTab v-else-if="activeTab === 'calendar'" :key="`calendar-${refreshKey}`" :branch-id="branchId" />
    <ClientsTab v-else-if="activeTab === 'clients'" :key="`clients-${refreshKey}`" :branch-id="branchId" />
    <InstallmentsTab v-else-if="activeTab === 'installments'" :key="`installments-${refreshKey}`" :branch-id="branchId" />
    <MaintenanceTab v-else-if="activeTab === 'maintenance'" :key="`maintenance-${refreshKey}`" :branch-id="branchId" />
    <RequestsTab v-else-if="activeTab === 'requests'" :key="`requests-${refreshKey}`" :branch-id="branchId" @changed="loadBadgeCounts" />
    <SupportTab v-else-if="activeTab === 'support'" :key="`support-${refreshKey}`" :branch-id="branchId" @changed="loadBadgeCounts" />
    <WaitlistTab v-else-if="activeTab === 'waitlist'" :key="`waitlist-${refreshKey}`" :branch-id="branchId" />
    <StaffTab v-else-if="activeTab === 'staff' && auth.hasRole('timeshare_admin')" :key="`staff-${refreshKey}`" :branch-id="branchId" />
    <UnitsTab v-else-if="activeTab === 'units' && auth.hasRole('timeshare_admin')" :key="`units-${refreshKey}`" :branch-id="branchId" />
  </div>
</template>

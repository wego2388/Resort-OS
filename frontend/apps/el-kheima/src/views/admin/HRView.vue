<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@resort-os/core'
import EmployeesTab from '../../components/hr/EmployeesTab.vue'
import AttendanceTab from '../../components/hr/AttendanceTab.vue'
import PayrollTab from '../../components/hr/PayrollTab.vue'
import LeavesTab from '../../components/hr/LeavesTab.vue'
import LeaderboardTab from '../../components/hr/LeaderboardTab.vue'
import RotaTab from '../../components/hr/RotaTab.vue'

const { t } = useI18n()
const auth = useAuthStore()
const branchId = computed(() => auth.branchId)
const tab = ref<'employees' | 'attendance' | 'payroll' | 'leaves' | 'leaderboard' | 'rota'>('employees')

const tabsList = computed<{ val: typeof tab.value; label: string }[]>(() => [
  { val: 'employees', label: t('backoffice.hr.tabs.employees') },
  { val: 'attendance', label: t('backoffice.hr.tabs.attendance') },
  { val: 'payroll', label: t('backoffice.hr.tabs.payroll') },
  { val: 'leaves', label: t('backoffice.hr.tabs.leaves') },
  { val: 'rota', label: `🗓️ ${t('backoffice.hr.tabs.rota')}` },
  { val: 'leaderboard', label: `🏆 ${t('backoffice.hr.tabs.leaderboard')}` },
])
</script>

<template>
  <div>
    <div class="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.hr.title') }}</h2>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.subtitle') }}</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl mb-6 w-fit">
      <button v-for="tabDef in tabsList" :key="tabDef.val"
        @click="tab = tabDef.val"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === tabDef.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300']"
      >{{ tabDef.label }}</button>
    </div>

    <!-- Employees Tab -->
    <EmployeesTab v-if="tab === 'employees'" :branch-id="branchId" />

    <!-- Payroll Tab -->
    <PayrollTab v-if="tab === 'payroll'" :branch-id="branchId" />

    <!-- Leaves Tab -->
    <LeavesTab v-if="tab === 'leaves'" :branch-id="branchId" />

    <!-- Attendance Tab -->
    <AttendanceTab v-if="tab === 'attendance'" :branch-id="branchId" />

    <!-- Rota Tab -->
    <RotaTab v-if="tab === 'rota'" :branch-id="branchId" />

    <!-- Leaderboard Tab -->
    <LeaderboardTab v-if="tab === 'leaderboard'" :branch-id="branchId" />
  </div>
</template>

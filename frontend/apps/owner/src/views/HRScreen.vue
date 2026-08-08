<script setup lang="ts">
/**
 * HRScreen — Phase 7c: قائمة الموظفين + رواتب + حضور aggregate
 * Decision 0004 §7c — قواعد عرض صارمة:
 *  ✅ full_name, position, department, hire_date, status
 *  ✅ net_salary, gross_salary, penalty_deduction, advance_deduction
 *  ✅ حضور aggregate (أيام حضور/غياب/تأخير/إجازة للشهر الحالي)
 *  ❌ national_id, employee_si, monthly_tax, phone, email
 */
import { ref, computed } from 'vue'
import { useOwnerHRSummary } from '../composables/useOwnerData'
import { formatMoney } from '../composables/useFormat'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'
import type { HREmployeeRow } from '../api/types'

const { data, loading, error, reload } = useOwnerHRSummary()

const searchQuery = ref('')
const filterStatus = ref<'all' | 'active' | 'on_leave' | 'terminated'>('active')

const statusLabel: Record<string, string> = {
  active:     'نشط',
  on_leave:   'إجازة',
  terminated: 'منتهي',
}

const statusStyle: Record<string, string> = {
  active:     'text-owner-green',
  on_leave:   'text-owner-amber',
  terminated: 'text-owner-muted',
}

const filtered = computed((): HREmployeeRow[] => {
  if (!data.value) return []
  let list = data.value.employees
  if (filterStatus.value !== 'all') {
    list = list.filter(e => e.status === filterStatus.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(e =>
      e.full_name.toLowerCase().includes(q) ||
      e.position.toLowerCase().includes(q) ||
      (e.department ?? '').toLowerCase().includes(q)
    )
  }
  return list
})

const expandedEmployees = ref<Set<number>>(new Set())
function toggleEmployee(id: number) {
  if (expandedEmployees.value.has(id)) expandedEmployees.value.delete(id)
  else expandedEmployees.value.add(id)
}

function formatHireDate(d: string) {
  return new Date(d).toLocaleDateString('ar-EG', { year: 'numeric', month: 'short' })
}
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden">
    <!-- Header summary bar -->
    <div v-if="data" class="flex gap-3 px-4 py-3 bg-owner-card border-b border-owner-border text-xs">
      <div class="text-center flex-1">
        <div class="font-bold text-owner-green text-base">{{ data.active_count }}</div>
        <div class="text-owner-muted">نشط</div>
      </div>
      <div class="text-center flex-1">
        <div class="font-bold text-owner-amber text-base">{{ data.on_leave_count }}</div>
        <div class="text-owner-muted">إجازة</div>
      </div>
      <div class="text-center flex-1">
        <div class="font-bold text-owner-text text-base">{{ formatMoney(data.total_net_payroll) }}</div>
        <div class="text-owner-muted">إجمالي الرواتب</div>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto overscroll-contain">
      <!-- Search + filter -->
      <div class="p-4 space-y-3">
        <input
          v-model="searchQuery"
          type="search"
          placeholder="ابحث باسم الموظف أو الوظيفة..."
          class="w-full bg-owner-card border border-owner-border rounded-xl px-4 py-2.5 text-sm text-owner-text outline-none focus:border-owner-green"
          dir="rtl"
        />
        <!-- Status filter chips -->
        <div class="flex gap-2">
          <button
            v-for="s in ['all', 'active', 'on_leave', 'terminated'] as const"
            :key="s"
            class="px-3 py-1 rounded-lg text-xs font-semibold transition-colors"
            :class="filterStatus === s
              ? 'bg-owner-green text-black'
              : 'bg-owner-bg text-owner-muted border border-owner-border'"
            @click="filterStatus = s"
          >
            {{ s === 'all' ? 'الكل' : statusLabel[s] }}
          </button>
        </div>
      </div>

      <ErrorState v-if="error && !loading" :message="error" @retry="reload" />
      <SkeletonCards v-else-if="loading && !data" />

      <div v-else-if="data" class="px-4 pb-6 space-y-3">
        <div v-if="filtered.length === 0" class="owner-card text-center py-6">
          <div class="text-sm text-owner-muted">لا توجد نتائج</div>
        </div>

        <!-- بطاقة موظف -->
        <div
          v-for="emp in filtered"
          :key="emp.employee_id"
          class="owner-card"
        >
          <!-- رأس البطاقة -->
          <button
            class="w-full flex items-center justify-between gap-2"
            @click="toggleEmployee(emp.employee_id)"
          >
            <div class="text-right flex-1 min-w-0">
              <div class="text-sm font-bold text-owner-text truncate">{{ emp.full_name }}</div>
              <div class="text-xs text-owner-muted mt-0.5">
                {{ emp.position }}
                <span v-if="emp.department"> · {{ emp.department }}</span>
              </div>
            </div>
            <div class="text-left shrink-0">
              <div
                class="text-xs font-semibold"
                :class="statusStyle[emp.status] ?? 'text-owner-muted'"
              >{{ statusLabel[emp.status] ?? emp.status }}</div>
              <div class="text-xs text-owner-muted">منذ {{ formatHireDate(emp.hire_date) }}</div>
            </div>
          </button>

          <!-- تفاصيل موسّعة -->
          <div
            v-if="expandedEmployees.has(emp.employee_id)"
            class="mt-3 pt-3 border-t border-owner-border space-y-3"
          >
            <!-- الراتب -->
            <div v-if="emp.payroll">
              <div class="text-xs text-owner-muted mb-2 font-semibold">آخر كشف رواتب</div>
              <div class="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <div class="text-owner-muted">الراتب الإجمالي</div>
                  <div class="font-mono font-semibold text-owner-text">{{ formatMoney(emp.payroll.gross_salary) }}</div>
                </div>
                <div>
                  <div class="text-owner-muted">الراتب الصافي</div>
                  <div class="font-mono font-semibold text-owner-green">{{ formatMoney(emp.payroll.net_salary) }}</div>
                </div>
                <div v-if="parseFloat(emp.payroll.penalty_deduction) > 0">
                  <div class="text-owner-muted">جزاءات</div>
                  <div class="font-mono text-owner-red">{{ formatMoney(emp.payroll.penalty_deduction) }}</div>
                </div>
                <div v-if="parseFloat(emp.payroll.advance_deduction) > 0">
                  <div class="text-owner-muted">خصم سلف</div>
                  <div class="font-mono text-owner-amber">{{ formatMoney(emp.payroll.advance_deduction) }}</div>
                </div>
              </div>
            </div>
            <div v-else class="text-xs text-owner-muted">لا يوجد كشف رواتب حتى الآن</div>

            <!-- الحضور الشهر الحالي -->
            <div v-if="emp.attendance_this_month">
              <div class="text-xs text-owner-muted mb-2 font-semibold">حضور الشهر الحالي</div>
              <div class="grid grid-cols-4 gap-2 text-xs text-center">
                <div>
                  <div class="font-bold text-owner-green text-sm">{{ emp.attendance_this_month.present_days }}</div>
                  <div class="text-owner-muted">حضور</div>
                </div>
                <div>
                  <div class="font-bold text-owner-red text-sm">{{ emp.attendance_this_month.absent_days }}</div>
                  <div class="text-owner-muted">غياب</div>
                </div>
                <div>
                  <div class="font-bold text-owner-amber text-sm">{{ emp.attendance_this_month.late_days }}</div>
                  <div class="text-owner-muted">تأخير</div>
                </div>
                <div>
                  <div class="font-bold text-owner-muted text-sm">{{ emp.attendance_this_month.leave_days }}</div>
                  <div class="text-owner-muted">إجازة</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="text-center text-xs text-owner-muted py-2">
          محسوب: {{ new Date(data.computed_at).toLocaleTimeString('ar-EG') }}
        </div>
      </div>
    </div>
  </div>
</template>

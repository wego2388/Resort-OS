<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const h = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const tab = ref<'leads' | 'customers' | 'campaigns'>('leads')

interface Lead {
  id: number; full_name: string; phone?: string; interest: string
  stage: string; created_at: string; assigned_to?: number
}
interface Customer {
  id: number; full_name: string; phone?: string; segment: string
  total_spent: number; visits_count: number; vip_flag?: boolean
}

const leads = ref<Lead[]>([])
const customers = ref<Customer[]>([])
const loading = ref(false)

const stageConfig: Record<string, { label: string; color: string }> = {
  new:       { label: 'جديد',        color: 'bg-gray-100 text-gray-700' },
  contacted: { label: 'تم التواصل', color: 'bg-blue-100 text-blue-700' },
  qualified: { label: 'مؤهل',        color: 'bg-purple-100 text-purple-700' },
  proposal:  { label: 'عرض',         color: 'bg-amber-100 text-amber-700' },
  won:       { label: 'مُغلق ✓',     color: 'bg-green-100 text-green-700' },
  lost:      { label: 'خسارة',       color: 'bg-red-100 text-red-700' },
}

const interestLabels: Record<string, string> = {
  timeshare: 'تايم شير', leasing: 'إيجار', booking: 'حجز', membership: 'عضوية', other: 'أخرى'
}

const segmentColors: Record<string, string> = {
  regular: 'bg-gray-100 text-gray-700', vip: 'bg-amber-100 text-amber-700',
  corporate: 'bg-blue-100 text-blue-700', travel_agent: 'bg-purple-100 text-purple-700',
}

async function loadLeads() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/crm/leads', { headers: h, params: { branch_id: branchId } })
    leads.value = res.data.leads ?? res.data.items ?? res.data
  } catch(e) { console.error(e) }
  finally { loading.value = false }
}

async function loadCustomers() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/crm/customers', { headers: h, params: { branch_id: branchId } })
    customers.value = res.data.customers ?? res.data.items ?? res.data
  } catch(e) { console.error(e) }
  finally { loading.value = false }
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'leads') await loadLeads()
  if (t === 'customers') await loadCustomers()
}

async function advanceLead(lead: Lead) {
  const flow: Record<string, string> = { new: 'contacted', contacted: 'qualified', qualified: 'proposal', proposal: 'won' }
  const next = flow[lead.stage]
  if (!next) return
  try {
    await axios.patch(`/api/v1/crm/leads/${lead.id}`, { stage: next }, { headers: h })
    lead.stage = next
  } catch(e) { console.error(e) }
}

onMounted(loadLeads)
</script>

<template>
  <div dir="rtl">
    <h2 class="text-2xl font-black text-gray-900 mb-6">إدارة العملاء — CRM</h2>

    <div class="flex gap-1 bg-stone-100 p-1 rounded-xl mb-6 w-fit">
      <button v-for="t in [{ val: 'leads', label: 'العملاء المحتملون' }, { val: 'customers', label: 'العملاء' }, { val: 'campaigns', label: 'الحملات' }]"
        :key="t.val" @click="loadTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === t.val ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700']"
      >{{ t.label }}</button>
    </div>

    <!-- Leads -->
    <div v-if="tab === 'leads'">
      <div v-if="loading" class="text-center py-12 text-gray-400">جاري التحميل...</div>
      <div v-else class="space-y-3">
        <div v-for="lead in leads" :key="lead.id"
          class="bg-white rounded-2xl border border-stone-200 p-4 shadow-sm flex items-center justify-between">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-gray-900">{{ lead.full_name }}</span>
              <span v-if="lead.phone" class="text-xs text-gray-400">{{ lead.phone }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full">{{ interestLabels[lead.interest] ?? lead.interest }}</span>
              <span class="text-gray-400">{{ new Date(lead.created_at).toLocaleDateString('ar-EG') }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span :class="['px-2 py-1 rounded-full text-xs font-medium', stageConfig[lead.stage]?.color ?? 'bg-gray-100 text-gray-600']">
              {{ stageConfig[lead.stage]?.label ?? lead.stage }}
            </span>
            <button v-if="!['won','lost'].includes(lead.stage)" @click="advanceLead(lead)"
              class="px-3 py-1 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700">
              تقدم ←
            </button>
          </div>
        </div>
        <div v-if="leads.length === 0" class="text-center py-12 text-gray-400">
          <div class="text-4xl mb-2">🤝</div><p>لا توجد عملاء محتملون</p>
        </div>
      </div>
    </div>

    <!-- Customers -->
    <div v-if="tab === 'customers'">
      <div v-if="loading" class="text-center py-12 text-gray-400">جاري التحميل...</div>
      <div v-else class="bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden">
        <table class="w-full">
          <thead class="bg-stone-50">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">العميل</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الشريحة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الزيارات</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">إجمالي الإنفاق</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in customers" :key="c.id" class="border-t border-stone-100 hover:bg-stone-50">
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <span v-if="c.vip_flag" class="text-amber-500 text-sm">⭐</span>
                  <div>
                    <div class="font-medium text-gray-900 text-sm">{{ c.full_name }}</div>
                    <div v-if="c.phone" class="text-xs text-gray-400">{{ c.phone }}</div>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3">
                <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', segmentColors[c.segment] ?? 'bg-gray-100 text-gray-600']">
                  {{ c.segment === 'vip' ? 'VIP' : c.segment === 'corporate' ? 'شركة' : c.segment === 'travel_agent' ? 'وكيل سفر' : 'عادي' }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-700 font-medium">{{ c.visits_count }}</td>
              <td class="px-4 py-3 text-sm font-bold text-blue-700">{{ Number(c.total_spent).toLocaleString('ar-EG') }} ج</td>
            </tr>
            <tr v-if="customers.length === 0">
              <td colspan="4" class="px-4 py-12 text-center text-gray-400">لا توجد عملاء</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Campaigns -->
    <div v-if="tab === 'campaigns'" class="bg-white rounded-2xl border border-stone-200 p-8 text-center text-gray-400 shadow-sm">
      <div class="text-4xl mb-3">📢</div>
      <p class="font-medium text-gray-600 mb-1">الحملات التسويقية</p>
      <p class="text-sm">سيتم تطوير إدارة الحملات قريباً</p>
    </div>
  </div>
</template>

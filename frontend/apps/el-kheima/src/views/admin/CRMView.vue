<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@resort-os/core'
import LeadsTab from '../../components/crm/LeadsTab.vue'
import CustomersTab from '../../components/crm/CustomersTab.vue'
import OpportunitiesTab from '../../components/crm/OpportunitiesTab.vue'
import ActivitiesTab from '../../components/crm/ActivitiesTab.vue'
import CampaignsTab from '../../components/crm/CampaignsTab.vue'
import GuestsTab from '../../components/crm/GuestsTab.vue'
import LoyaltyTab from '../../components/crm/LoyaltyTab.vue'

const { t } = useI18n()
const auth = useAuthStore()
const branchId = computed(() => auth.branchId)
const tab = ref<'leads' | 'customers' | 'opportunities' | 'activities' | 'campaigns' | 'guests' | 'loyalty'>('leads')

const tabsList = computed<{ val: typeof tab.value; label: string }[]>(() => [
  { val: 'leads', label: t('backoffice.crm.tabs.leads') },
  { val: 'customers', label: t('backoffice.crm.tabs.customers') },
  { val: 'opportunities', label: t('backoffice.crm.tabs.opportunities') },
  { val: 'activities', label: t('backoffice.crm.tabs.activities') },
  { val: 'campaigns', label: t('backoffice.crm.tabs.campaigns') },
  { val: 'guests', label: t('backoffice.crm.tabs.guests') },
  { val: 'loyalty', label: `🎁 ${t('backoffice.crm.tabs.loyalty')}` },
])
</script>

<template>
  <div>
    <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100 mb-6">{{ t('backoffice.crm.title') }}</h2>

    <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
      <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl w-fit">
        <button v-for="tabDef in tabsList"
          :key="tabDef.val" @click="tab = tabDef.val"
          :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === tabDef.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300']"
        >{{ tabDef.label }}</button>
      </div>
    </div>

    <!-- Leads -->
    <LeadsTab v-if="tab === 'leads'" :branch-id="branchId" />

    <!-- Customers -->
    <CustomersTab v-if="tab === 'customers'" :branch-id="branchId" />

    <!-- Opportunities -->
    <OpportunitiesTab v-if="tab === 'opportunities'" :branch-id="branchId" />

    <!-- Activities -->
    <ActivitiesTab v-if="tab === 'activities'" :branch-id="branchId" />

    <!-- Guest Profiles (PMS checkout integration — read-only) -->
    <GuestsTab v-if="tab === 'guests'" :branch-id="branchId" />

    <!-- Campaigns -->
    <CampaignsTab v-if="tab === 'campaigns'" :branch-id="branchId" />

    <!-- Loyalty -->
    <LoyaltyTab v-if="tab === 'loyalty'" :branch-id="branchId" />
  </div>
</template>

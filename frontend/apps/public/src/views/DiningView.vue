<script setup lang="ts">
/**
 * Dining / menu page for the public marketing site — pulls real menu data
 * (seeded 2026-07-01, see backend/app/seed.py::_seed_menus) from the unified
 * dining module's public, unauthenticated endpoints:
 *   - GET /api/v1/dining/public/outlets (which outlet_ids exist for the branch)
 *   - GET /api/v1/dining/public/menu?outlet_id=... (categories + items, one per outlet)
 * Same fetching pattern as the Rooms section in HomeView.vue: plain axios
 * (not @resort-os/core's api client — this app is deliberately
 * unauthenticated-only), PUBLIC_BRANCH_ID for the single seeded branch.
 *
 * DINING_CUTOVER_PLAN.md Batch 6 (2026-07-13): used to call
 * /api/v1/restaurant/public/menu + /api/v1/cafe/public/menu directly (two
 * fixed outlets, hardcoded rendering — flat grid for restaurant, grouped-by-
 * category for cafe). Both deleted along with the restaurant/cafe modules.
 * Now generalized to any number of outlets: one grouped-by-category section
 * per outlet, in outlet order — no more hardcoded "restaurant" vs "cafe"
 * layout branch.
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'
import { PUBLIC_BRANCH_ID } from '../constants/resort'

const { t, locale } = useI18n()

interface PublicMenuItem {
  id: number
  name: string
  name_ar: string | null
  price: string
  is_available: boolean
  category_id: number | null
}

interface PublicMenuCategory {
  id: number
  name: string
  name_ar: string | null
}

interface PublicMenuResponse {
  branch_id: number
  outlet_id: number
  outlet_name: string
  outlet_name_ar: string | null
  categories: PublicMenuCategory[]
  items: PublicMenuItem[]
}

interface PublicOutlet {
  id: number
  name: string
  name_ar: string | null
  outlet_type: string
}

interface OutletMenu {
  outlet: PublicOutlet
  categories: PublicMenuCategory[]
  items: PublicMenuItem[]
}

const outletMenus = ref<OutletMenu[]>([])
const loading = ref(true)
const error = ref(false)

function itemName(item: PublicMenuItem): string {
  return locale.value === 'ar' && item.name_ar ? item.name_ar : item.name
}

function categoryName(cat: PublicMenuCategory): string {
  return locale.value === 'ar' && cat.name_ar ? cat.name_ar : cat.name
}

function outletName(o: PublicOutlet): string {
  return locale.value === 'ar' && o.name_ar ? o.name_ar : o.name
}

function formatPrice(price: string): string {
  const n = Number(price)
  return Number.isFinite(n) ? n.toLocaleString(locale.value === 'ar' ? 'ar-EG' : 'en-US') : price
}

// كل منفذ بيتعرض مقسّم حسب فئاته (نفس ترتيب sort_order من الباك إند —
// راجع dining.crud.list_categories) — بديل عن الفصل الثابت مطعم/كافيه القديم.
function groupedByCategory(menu: OutletMenu) {
  return menu.categories
    .map((cat) => ({ category: cat, items: menu.items.filter((i) => i.category_id === cat.id) }))
    .filter((g) => g.items.length > 0)
}

const hasAnyItems = computed(() => outletMenus.value.some((m) => m.items.length > 0))

onMounted(async () => {
  try {
    const { data: outlets } = await axios.get<PublicOutlet[]>('/api/v1/dining/public/outlets', {
      params: { branch_id: PUBLIC_BRANCH_ID },
    })
    const menus = await Promise.all(
      outlets.map(async (outlet) => {
        const { data } = await axios.get<PublicMenuResponse>('/api/v1/dining/public/menu', {
          params: { outlet_id: outlet.id },
        })
        return { outlet, categories: data.categories, items: data.items }
      }),
    )
    outletMenus.value = menus
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="min-h-screen bg-white">
    <SiteHeader />

    <div class="bg-gradient-to-br from-brand-charcoal via-brand-ocean to-brand-teal text-white">
      <div class="max-w-4xl mx-auto text-center px-6 py-16">
        <h1 class="font-heading text-3xl md:text-5xl font-black mb-4">{{ t('marketing.dining.title') }}</h1>
        <p class="text-white/90 text-lg font-body">{{ t('marketing.dining.subtitle') }}</p>
      </div>
    </div>

    <div v-if="loading" class="text-center text-gray-400 py-20">
      <div class="animate-spin h-8 w-8 border-2 border-brand-ocean border-t-transparent rounded-full mx-auto mb-3"/>
      {{ t('marketing.dining.loading') }}
    </div>

    <div v-else-if="error" class="max-w-2xl mx-auto text-center text-red-500 bg-red-50 rounded-2xl my-16 py-10 px-6">
      {{ t('marketing.dining.error') }}
    </div>

    <div v-else-if="!hasAnyItems" class="max-w-2xl mx-auto text-center text-gray-400 bg-stone-50 rounded-2xl my-16 py-10 px-6">
      {{ t('marketing.dining.empty') }}
    </div>

    <template v-else>
      <!-- منفذ واحد لكل قسم، متبادل بين خلفية بيضاء/رمادية فاتحة عشان يبان
           الفصل بصريًا من غير الاعتماد على نوع ثابت (مطعم/كافيه) -->
      <div v-for="(menu, idx) in outletMenus" :key="menu.outlet.id"
        v-show="menu.items.length" :class="idx % 2 === 1 ? 'bg-brand-lightgray/50' : ''" class="py-16">
        <div class="max-w-5xl mx-auto px-6">
          <h2 class="font-heading text-3xl font-black text-brand-charcoal text-center mb-2">{{ outletName(menu.outlet) }}</h2>
          <p class="text-gray-500 text-center mb-6 font-body">{{ t('marketing.dining.outletSubtitle') }}</p>

          <!-- Quick category nav -->
          <div v-if="groupedByCategory(menu).length > 1" class="flex flex-wrap justify-center gap-2 mb-12">
            <a v-for="group in groupedByCategory(menu)" :key="`nav-${menu.outlet.id}-${group.category.id}`"
              :href="`#cat-${menu.outlet.id}-${group.category.id}`"
              class="text-xs font-bold bg-white border border-stone-200 text-brand-teal px-3 py-1.5 rounded-full hover:bg-brand-teal hover:text-white hover:border-brand-teal transition-colors">
              {{ categoryName(group.category) }}
            </a>
          </div>

          <div class="space-y-12">
            <div v-for="group in groupedByCategory(menu)" :key="group.category.id"
              :id="`cat-${menu.outlet.id}-${group.category.id}`" class="scroll-mt-24">
              <h3 class="font-heading font-black text-brand-charcoal text-xl mb-4 pb-2 border-b-2 border-brand-sandy inline-block">
                {{ categoryName(group.category) }}
              </h3>
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                <div v-for="item in group.items" :key="`i-${item.id}`"
                  class="bg-white rounded-xl border border-stone-200 px-4 py-3 flex items-center justify-between gap-3 hover:shadow-sm transition-shadow">
                  <span class="font-body font-semibold text-brand-charcoal text-sm">{{ itemName(item) }}</span>
                  <span class="font-heading font-black text-brand-ocean text-sm whitespace-nowrap">
                    {{ formatPrice(item.price) }} <span class="text-[10px] font-semibold text-gray-400">EGP</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- CTA -->
    <div class="bg-gradient-to-r from-brand-ocean to-brand-teal py-16 text-center px-6">
      <h2 class="font-heading text-3xl font-black text-white mb-4">{{ t('marketing.cta.title') }}</h2>
      <p class="text-white/90 mb-8 text-lg font-body">{{ t('marketing.cta.subtitle') }}</p>
      <RouterLink to="/book"
        class="inline-block bg-white text-brand-ocean px-10 py-4 rounded-2xl font-black text-lg hover:bg-brand-lightgray transition-colors">
        {{ t('marketing.cta.button') }}
      </RouterLink>
    </div>

    <SiteFooter />
  </div>
</template>

<script setup lang="ts">
/**
 * Public marketing landing page for El Kheima Beach Resort.
 * Content sourced from /home/wego/projects/elkheima-beach-resort-marketing/
 * (01_brand, 05_content) via src/i18n/marketing.ts — see that file's header
 * comment for exact provenance per locale.
 */
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'
import { PUBLIC_BRANCH_ID } from '../constants/resort'

const { t, locale } = useI18n()

interface RoomType {
  id: number
  branch_id: number
  name: string
  name_ar: string | null
  base_rate: string
  max_occupancy: number
  amenities: string | null
  is_active: boolean
}

const rooms = ref<RoomType[]>([])
const roomsLoading = ref(true)
const roomsError = ref(false)

function roomName(r: RoomType): string {
  return locale.value === 'ar' && r.name_ar ? r.name_ar : r.name
}

function roomAmenities(r: RoomType): string[] {
  // amenities مخزّن كـ JSON list في الباك إند (RoomType.amenities: Text, "JSON list")
  // — لازم JSON.parse مش split(',') العادي، وإلا كل tag بيطلع فيه براكيت/quotes حرفية.
  if (!r.amenities) return []
  try {
    const parsed = JSON.parse(r.amenities)
    if (!Array.isArray(parsed)) return []
    return parsed.map((a) => String(a).replace(/_/g, ' ')).filter(Boolean)
  } catch {
    return r.amenities.split(',').map((a) => a.trim()).filter(Boolean)
  }
}

function formatRate(rate: string): string {
  const n = Number(rate)
  return Number.isFinite(n) ? n.toLocaleString(locale.value === 'ar' ? 'ar-EG' : 'en-US') : rate
}

const cheapestRoomFrom = computed(() => {
  if (!rooms.value.length) return null
  return Math.min(...rooms.value.map(r => Number(r.base_rate)))
})

onMounted(async () => {
  try {
    const { data } = await axios.get<RoomType[]>('/api/v1/pms/public/room-types', {
      params: { branch_id: PUBLIC_BRANCH_ID },
    })
    rooms.value = data
  } catch {
    roomsError.value = true
  } finally {
    roomsLoading.value = false
  }
})

const FEATURE_KEYS = ['beach', 'dining', 'water', 'rooms', 'events', 'families'] as const
const FEATURE_ICONS: Record<typeof FEATURE_KEYS[number], string> = {
  beach: '🏖️', dining: '🍝', water: '🤿', rooms: '🌊', events: '💍', families: '👨‍👩‍👧‍👦',
}
</script>

<template>
  <div class="min-h-screen bg-white">
    <SiteHeader />

    <!-- Hero -->
    <div class="relative bg-gradient-to-br from-brand-charcoal via-brand-ocean to-brand-teal text-white overflow-hidden">
      <div class="absolute inset-0 opacity-20">
        <div class="absolute top-10 end-10 w-64 h-64 bg-brand-sunset rounded-full blur-3xl"/>
        <div class="absolute bottom-0 start-0 w-96 h-96 bg-brand-sandy rounded-full blur-3xl"/>
      </div>
      <div class="relative max-w-3xl mx-auto text-center px-6 py-20 sm:py-28">
        <p class="uppercase tracking-widest text-brand-sandy text-xs sm:text-sm font-bold mb-4">{{ t('marketing.hero.eyebrow') }}</p>
        <h1 class="font-heading text-4xl md:text-6xl font-black mb-4 leading-tight">{{ t('marketing.hero.title') }}</h1>
        <p class="text-white/90 text-lg md:text-xl mb-10 font-body">{{ t('marketing.hero.subtitle') }}</p>
        <div class="flex flex-col sm:flex-row gap-3 justify-center">
          <RouterLink to="/book"
            class="inline-block bg-brand-sunset text-white px-10 py-4 rounded-2xl font-black text-lg hover:brightness-110 transition-all hover:shadow-xl hover:-translate-y-0.5">
            {{ t('marketing.hero.cta') }}
          </RouterLink>
          <a href="#rooms"
            class="inline-block bg-white/10 border border-white/30 text-white px-10 py-4 rounded-2xl font-black text-lg hover:bg-white/20 transition-all">
            {{ t('marketing.nav.rooms') }}
          </a>
        </div>
      </div>

      <!-- Stats strip -->
      <div class="relative border-t border-white/15 bg-black/10">
        <div class="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-6 px-6 py-8 text-center">
          <div>
            <p class="font-heading text-2xl sm:text-3xl font-black text-brand-sandy">{{ t('marketing.stats.beachArea') }}</p>
            <p class="text-xs sm:text-sm text-white/80 mt-1">{{ t('marketing.stats.beachAreaLabel') }}</p>
          </div>
          <div>
            <p class="font-heading text-2xl sm:text-3xl font-black text-brand-sandy">{{ t('marketing.stats.beachLength') }}</p>
            <p class="text-xs sm:text-sm text-white/80 mt-1">{{ t('marketing.stats.beachLengthLabel') }}</p>
          </div>
          <div>
            <p class="font-heading text-2xl sm:text-3xl font-black text-brand-sandy">{{ t('marketing.stats.totalArea') }}</p>
            <p class="text-xs sm:text-sm text-white/80 mt-1">{{ t('marketing.stats.totalAreaLabel') }}</p>
          </div>
          <div>
            <p class="font-heading text-2xl sm:text-3xl font-black text-brand-sandy">{{ t('marketing.stats.ranking') }}</p>
            <p class="text-xs sm:text-sm text-white/80 mt-1">{{ t('marketing.stats.rankingLabel') }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- About -->
    <div class="max-w-3xl mx-auto px-6 py-16 text-center">
      <h2 class="font-heading text-3xl font-black text-brand-charcoal mb-5">{{ t('marketing.about.title') }}</h2>
      <p class="text-gray-600 leading-relaxed font-body">{{ t('marketing.about.body') }}</p>
    </div>

    <!-- Value props -->
    <div class="bg-brand-lightgray/50 py-16">
      <div class="max-w-5xl mx-auto px-6">
        <h2 class="font-heading text-3xl font-black text-brand-charcoal text-center mb-2">{{ t('marketing.valueProps.title') }}</h2>
        <p class="text-gray-500 text-center mb-10 font-body">{{ t('marketing.valueProps.subtitle') }}</p>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div v-for="key in FEATURE_KEYS" :key="key"
            class="text-center p-6 bg-white rounded-2xl border border-stone-200 shadow-sm hover:shadow-md transition-shadow">
            <div class="text-4xl mb-3">{{ FEATURE_ICONS[key] }}</div>
            <h3 class="font-heading font-bold text-brand-charcoal text-lg mb-2">{{ t(`marketing.valueProps.${key}.title`) }}</h3>
            <p class="text-gray-500 text-sm leading-relaxed font-body">{{ t(`marketing.valueProps.${key}.desc`) }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Rooms — live data from GET /pms/public/room-types -->
    <div id="rooms" class="max-w-5xl mx-auto px-6 py-16 scroll-mt-20">
      <h2 class="font-heading text-3xl font-black text-brand-charcoal text-center mb-2">{{ t('marketing.rooms.title') }}</h2>
      <p class="text-gray-500 text-center mb-10 font-body">{{ t('marketing.rooms.subtitle') }}</p>

      <div v-if="roomsLoading" class="text-center text-gray-400 py-12">
        <div class="animate-spin h-8 w-8 border-2 border-brand-ocean border-t-transparent rounded-full mx-auto mb-3"/>
        {{ t('marketing.rooms.loading') }}
      </div>

      <div v-else-if="roomsError" class="text-center text-red-500 bg-red-50 rounded-2xl py-10 px-6">
        {{ t('marketing.rooms.error') }}
      </div>

      <div v-else-if="!rooms.length" class="text-center text-gray-400 bg-stone-50 rounded-2xl py-10 px-6">
        {{ t('marketing.rooms.empty') }}
      </div>

      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        <div v-for="room in rooms" :key="room.id"
          class="bg-white rounded-2xl border border-stone-200 shadow-sm hover:shadow-lg transition-shadow overflow-hidden flex flex-col">
          <div class="h-2 bg-gradient-to-r from-brand-ocean to-brand-teal" />
          <div class="p-6 flex flex-col flex-1">
            <h3 class="font-heading font-bold text-brand-charcoal text-lg mb-1">{{ roomName(room) }}</h3>
            <p class="text-xs text-gray-400 mb-4 font-body">{{ t('marketing.rooms.maxGuests', { n: room.max_occupancy }) }}</p>

            <div v-if="roomAmenities(room).length" class="flex flex-wrap gap-1.5 mb-4">
              <span v-for="a in roomAmenities(room)" :key="a"
                class="text-[11px] font-semibold bg-brand-lightgray text-brand-teal px-2 py-1 rounded-full">{{ a }}</span>
            </div>

            <div class="mt-auto pt-4 border-t border-stone-100 flex items-end justify-between">
              <div>
                <p class="text-[11px] text-gray-400 uppercase tracking-wide">{{ t('marketing.rooms.from') }}</p>
                <p class="font-heading font-black text-brand-ocean text-xl">
                  {{ formatRate(room.base_rate) }} <span class="text-xs font-semibold text-gray-400">EGP</span>
                </p>
                <p class="text-[11px] text-gray-400">{{ t('marketing.rooms.perNight') }}</p>
              </div>
              <RouterLink to="/book"
                class="bg-brand-charcoal text-white text-xs font-bold px-4 py-2.5 rounded-xl hover:bg-brand-ocean transition-colors">
                {{ t('marketing.rooms.bookThis') }}
              </RouterLink>
            </div>
          </div>
        </div>
      </div>

      <p v-if="!roomsLoading && !roomsError && cheapestRoomFrom !== null" class="text-center text-xs text-gray-400 mt-8 font-body">
        {{ t('marketing.rooms.from') }} {{ formatRate(String(cheapestRoomFrom)) }} EGP {{ t('marketing.rooms.perNight') }}
      </p>
    </div>

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

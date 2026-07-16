<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const branchId = auth.branchId
const tab = ref<'bookings' | 'offers' | 'pages' | 'blog' | 'contact'>('bookings')

// ── Interfaces ────────────────────────────────────────────────────────
interface OnlineBooking {
  id: number; offer_id: number | null; guest_name: string; guest_phone: string
  guest_email: string | null; guests_count: number; requested_date: string
  status: string; source: string; total_amount: number
  confirmed_by: number | null; confirmed_at: string | null
  notes: string | null; created_at: string; updated_at: string
}
interface HubOffer {
  id: number; title: string; title_ar: string | null; offer_type: string
  original_price: number; offer_price: number; valid_from: string; valid_until: string
  max_bookings: number; bookings_count: number; is_active: boolean
  image_url: string | null; created_at: string
}
interface HubPage {
  id: number; slug: string; title: string; title_ar: string | null
  page_type: string; is_published: boolean; published_at: string | null
  sort_order: number; updated_at: string
}

// ── State ─────────────────────────────────────────────────────────────
const loading = ref(false)

// Bookings
const bookings = ref<OnlineBooking[]>([])
const bookingsTotal = ref(0)
const bookingPage = ref(1)
const bookingStatus = ref<string>('')
const bookingDateFrom = ref('')
const bookingDateTo = ref('')

// Offers
const offers = ref<HubOffer[]>([])
const offerActiveOnly = ref(false)
const offerModal = ref(false)
const editingOffer = ref<HubOffer | null>(null)
const savingOffer = ref(false)
const offerForm = ref({
  title: '', title_ar: '', offer_type: 'room', description: '',
  original_price: '', offer_price: '', valid_from: '', valid_until: '',
  max_bookings: '-1', image_url: '', is_active: true,
})

// Pages
const pages = ref<HubPage[]>([])
const pageModal = ref(false)
const editingPage = ref<HubPage | null>(null)
const savingPage = ref(false)
const pageForm = ref({
  slug: '', title: '', title_ar: '', page_type: 'info',
  meta_desc: '', sort_order: '100', is_published: false,
})

// ── Config ────────────────────────────────────────────────────────────
const bookingStatusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  pending:   { label: 'معلّق',   variant: 'warning' },
  confirmed: { label: 'مؤكَّد',  variant: 'success' },
  cancelled: { label: 'ملغي',    variant: 'danger' },
  no_show:   { label: 'لم يحضر', variant: 'neutral' },
}
const offerTypeLabels: Record<string, string> = {
  room: 'غرفة', beach: 'شاطئ', restaurant: 'مطعم', package: 'باقة', event: 'فعالية',
}
const pageTypeLabels: Record<string, string> = {
  info: 'معلومات', offer: 'عروض', news: 'أخبار', gallery: 'معرض صور', contact: 'تواصل',
}
const sourceLabels: Record<string, string> = {
  website: 'الموقع', whatsapp: 'واتساب', instagram: 'إنستجرام', tiktok: 'تيك توك', other: 'أخرى',
}

// ── Computed ──────────────────────────────────────────────────────────
const isOfferActive = (o: HubOffer) => {
  const now = new Date().toISOString().slice(0, 10)
  return o.is_active && o.valid_until >= now
}

// ── Loaders ───────────────────────────────────────────────────────────
async function loadBookings() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      branch_id: branchId, page: bookingPage.value, size: 30,
    }
    if (bookingStatus.value) params.status = bookingStatus.value
    if (bookingDateFrom.value) params.date_from = bookingDateFrom.value
    if (bookingDateTo.value) params.date_to = bookingDateTo.value
    const { data } = await api.get(ENDPOINTS.hub.onlineBookings, { params })
    bookings.value = data.items ?? []
    bookingsTotal.value = data.total ?? 0
  } catch { bookings.value = [] }
  finally { loading.value = false }
}

async function loadOffers() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.hub.offers, {
      params: { branch_id: branchId, active_only: offerActiveOnly.value, size: 100 }
    })
    offers.value = data.items ?? []
  } catch { offers.value = [] }
  finally { loading.value = false }
}

async function loadPages() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.hub.pages, {
      params: { branch_id: branchId, size: 100 }
    })
    pages.value = data.items ?? []
  } catch { pages.value = [] }
  finally { loading.value = false }
}

async function switchTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'bookings') await loadBookings()
  else if (t === 'offers') await loadOffers()
  else if (t === 'pages') await loadPages()
  else if (t === 'blog') await loadBlogPosts()
  else if (t === 'contact') await loadContactMessages()
}

// ── Blog Posts ────────────────────────────────────────────────────────
interface BlogPost {
  id: number; title: string; title_ar?: string | null; slug: string
  excerpt?: string | null; is_published: boolean; published_at?: string | null
  created_at: string
}
const blogPosts = ref<BlogPost[]>([])
const showBlogModal = ref(false)
const editingBlog = ref<BlogPost | null>(null)
const savingBlog = ref(false)
const blogForm = ref({ title: '', title_ar: '', slug: '', excerpt: '', is_published: false })

async function loadBlogPosts() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.hub.blogPosts, { params: { branch_id: branchId, size: 50 } })
    blogPosts.value = data.items ?? data ?? []
  } catch { blogPosts.value = [] }
  finally { loading.value = false }
}

function openCreateBlog() {
  editingBlog.value = null
  blogForm.value = { title: '', title_ar: '', slug: '', excerpt: '', is_published: false }
  showBlogModal.value = true
}

function openEditBlog(p: BlogPost) {
  editingBlog.value = p
  blogForm.value = { title: p.title, title_ar: p.title_ar ?? '', slug: p.slug, excerpt: p.excerpt ?? '', is_published: p.is_published }
  showBlogModal.value = true
}

async function saveBlogPost() {
  if (!blogForm.value.title.trim() || !blogForm.value.slug.trim()) {
    toast.error('العنوان والـ slug مطلوبان'); return
  }
  savingBlog.value = true
  try {
    if (editingBlog.value) {
      const { data } = await api.patch(ENDPOINTS.hub.blogPost(editingBlog.value.id), {
        title: blogForm.value.title,
        title_ar: blogForm.value.title_ar || null,
        excerpt: blogForm.value.excerpt || null,
        is_published: blogForm.value.is_published,
      })
      blogPosts.value = blogPosts.value.map(p => p.id === editingBlog.value!.id ? data : p)
      toast.success('تم تحديث المقال')
    } else {
      const { data } = await api.post(ENDPOINTS.hub.blogPosts, {
        branch_id: branchId,
        title: blogForm.value.title,
        title_ar: blogForm.value.title_ar || null,
        slug: blogForm.value.slug,
        excerpt: blogForm.value.excerpt || null,
        is_published: blogForm.value.is_published,
      })
      blogPosts.value = [data, ...blogPosts.value]
      toast.success('تم إنشاء المقال')
    }
    showBlogModal.value = false
  } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ') }
  finally { savingBlog.value = false }
}

async function deleteBlogPost(p: BlogPost) {
  const ok = await confirm({ message: `حذف مقال "${p.title}"؟`, danger: true, confirmText: 'حذف' })
  if (!ok) return
  try {
    await api.delete(ENDPOINTS.hub.blogPost(p.id))
    blogPosts.value = blogPosts.value.filter(x => x.id !== p.id)
    toast.success('تم الحذف')
  } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف') }
}

// ── Contact Messages ──────────────────────────────────────────────────
interface ContactMessage {
  id: number; name: string; email: string; phone?: string | null
  subject?: string | null; message: string; is_read: boolean; created_at: string
}
const contactMessages = ref<ContactMessage[]>([])
const contactUnread = ref(0)

async function loadContactMessages() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.hub.contact, { params: { branch_id: branchId, size: 50 } })
    contactMessages.value = data.items ?? data ?? []
    contactUnread.value = contactMessages.value.filter(m => !m.is_read).length
  } catch { contactMessages.value = [] }
  finally { loading.value = false }
}

// ── Booking Actions ────────────────────────────────────────────────────
async function confirmBooking(b: OnlineBooking) {
  const ok = await confirm({ message: `تأكيد حجز ${b.guest_name}؟`, confirmText: 'تأكيد' })
  if (!ok) return
  try {
    await api.post(ENDPOINTS.hub.onlineBookingConfirm(b.id))
    toast.success('تم تأكيد الحجز')
    await loadBookings()
  } catch(e: any) { toast.error(e?.response?.data?.detail ?? 'تعذّر التأكيد') }
}

async function cancelBooking(b: OnlineBooking) {
  const ok = await confirm({ message: `إلغاء حجز ${b.guest_name}؟`, danger: true, confirmText: 'إلغاء الحجز' })
  if (!ok) return
  try {
    await api.post(ENDPOINTS.hub.onlineBookingCancel(b.id))
    toast.success('تم الإلغاء')
    await loadBookings()
  } catch(e: any) { toast.error(e?.response?.data?.detail ?? 'تعذّر الإلغاء') }
}

// ── Offer Actions ──────────────────────────────────────────────────────
function openCreateOffer() {
  editingOffer.value = null
  offerForm.value = { title: '', title_ar: '', offer_type: 'room', description: '',
    original_price: '', offer_price: '', valid_from: '', valid_until: '',
    max_bookings: '-1', image_url: '', is_active: true }
  offerModal.value = true
}
function openEditOffer(o: HubOffer) {
  editingOffer.value = o
  offerForm.value = { title: o.title, title_ar: o.title_ar ?? '', offer_type: o.offer_type,
    description: '', original_price: String(o.original_price), offer_price: String(o.offer_price),
    valid_from: o.valid_from, valid_until: o.valid_until, max_bookings: String(o.max_bookings),
    image_url: o.image_url ?? '', is_active: o.is_active }
  offerModal.value = true
}

async function saveOffer() {
  if (!offerForm.value.title || !offerForm.value.original_price || !offerForm.value.offer_price) {
    toast.error('العنوان، السعر الأصلي، وسعر العرض إلزامية'); return
  }
  savingOffer.value = true
  try {
    if (editingOffer.value) {
      await api.patch(ENDPOINTS.hub.offer(editingOffer.value.id), {
        title: offerForm.value.title,
        offer_price: offerForm.value.offer_price,
        valid_until: offerForm.value.valid_until,
        max_bookings: parseInt(offerForm.value.max_bookings),
        is_active: offerForm.value.is_active,
        image_url: offerForm.value.image_url || null,
      })
      toast.success('تم تحديث العرض')
    } else {
      await api.post(ENDPOINTS.hub.offers, {
        branch_id: branchId,
        title: offerForm.value.title,
        title_ar: offerForm.value.title_ar || null,
        offer_type: offerForm.value.offer_type,
        original_price: offerForm.value.original_price,
        offer_price: offerForm.value.offer_price,
        valid_from: offerForm.value.valid_from,
        valid_until: offerForm.value.valid_until,
        max_bookings: parseInt(offerForm.value.max_bookings),
        image_url: offerForm.value.image_url || null,
      })
      toast.success('تم إنشاء العرض')
    }
    offerModal.value = false
    await loadOffers()
  } catch(e: any) { toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ') }
  finally { savingOffer.value = false }
}

// ── Page Actions ───────────────────────────────────────────────────────
function openCreatePage() {
  editingPage.value = null
  pageForm.value = { slug: '', title: '', title_ar: '', page_type: 'info',
    meta_desc: '', sort_order: '100', is_published: false }
  pageModal.value = true
}
function openEditPage(p: HubPage) {
  editingPage.value = p
  pageForm.value = { slug: p.slug, title: p.title, title_ar: p.title_ar ?? '',
    page_type: p.page_type, meta_desc: '', sort_order: String(p.sort_order),
    is_published: p.is_published }
  pageModal.value = true
}

async function savePage() {
  if (!pageForm.value.title || !pageForm.value.slug) {
    toast.error('العنوان والـ slug إلزاميان'); return
  }
  savingPage.value = true
  try {
    if (editingPage.value) {
      await api.patch(ENDPOINTS.hub.page(editingPage.value.id), {
        title: pageForm.value.title,
        title_ar: pageForm.value.title_ar || null,
        meta_desc: pageForm.value.meta_desc || null,
        sort_order: parseInt(pageForm.value.sort_order),
        is_published: pageForm.value.is_published,
      })
      toast.success('تم تحديث الصفحة')
    } else {
      await api.post(ENDPOINTS.hub.pages, {
        branch_id: branchId,
        slug: pageForm.value.slug,
        title: pageForm.value.title,
        title_ar: pageForm.value.title_ar || null,
        page_type: pageForm.value.page_type,
        meta_desc: pageForm.value.meta_desc || null,
        sort_order: parseInt(pageForm.value.sort_order),
      })
      toast.success('تم إنشاء الصفحة')
    }
    pageModal.value = false
    await loadPages()
  } catch(e: any) { toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ') }
  finally { savingPage.value = false }
}

async function deletePage(p: HubPage) {
  const ok = await confirm({ message: `حذف صفحة "${p.title}"؟`, danger: true, confirmText: 'حذف' })
  if (!ok) return
  try {
    await api.delete(ENDPOINTS.hub.page(p.id))
    toast.success('تم الحذف')
    await loadPages()
  } catch(e: any) { toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف') }
}

function fmtDate(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ar-EG')
}
function fmtMoney(n: number) {
  return n.toLocaleString('ar-EG', { maximumFractionDigits: 0 })
}

onMounted(() => switchTab('bookings'))
</script>

<template>
  <div dir="rtl" class="space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-black text-gray-800 dark:text-gray-200">الموقع والحجوزات الأونلاين</h1>
        <p class="text-sm text-gray-500 dark:text-gray-500 mt-1">إدارة حجوزات الموقع، العروض، والصفحات</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl w-fit">
      <button v-for="t in [
        { val: 'bookings', label: '📅 الحجوزات الأونلاين' },
        { val: 'offers',   label: '🎁 العروض' },
        { val: 'pages',    label: '📄 الصفحات' },
        { val: 'blog',     label: '✍️ المدونة' },
        { val: 'contact',  label: '📬 رسائل التواصل' },
      ]" :key="t.val" @click="switchTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all',
          tab === t.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 hover:text-gray-700']"
      >{{ t.label }}</button>
    </div>

    <!-- ══ TAB: BOOKINGS ══ -->
    <div v-if="tab === 'bookings'" class="space-y-4">
      <!-- Filters -->
      <div class="flex flex-wrap gap-3 items-center">
        <select v-model="bookingStatus" @change="loadBookings"
          class="border border-gray-300 rounded-lg px-3 py-2 text-sm">
          <option value="">جميع الحالات</option>
          <option value="pending">معلّق</option>
          <option value="confirmed">مؤكَّد</option>
          <option value="cancelled">ملغي</option>
          <option value="no_show">لم يحضر</option>
        </select>
        <input type="date" v-model="bookingDateFrom" @change="loadBookings"
          class="border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="من" />
        <input type="date" v-model="bookingDateTo" @change="loadBookings"
          class="border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="إلى" />
        <span class="text-sm text-gray-500 dark:text-gray-500">{{ bookingsTotal }} حجز</span>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <EmptyState v-if="!bookings.length" icon="📅" title="لا توجد حجوزات" subtitle="لم يصل أي حجز من الموقع بعد" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الضيف</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">التاريخ المطلوب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">أشخاص</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">المصدر</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الإجراء</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in bookings" :key="b.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3">
                  <div class="font-semibold text-sm text-gray-900 dark:text-gray-100">{{ b.guest_name }}</div>
                  <div class="text-xs text-gray-500 dark:text-gray-500">{{ b.guest_phone }}</div>
                  <div v-if="b.guest_email" class="text-xs text-gray-400 dark:text-gray-500">{{ b.guest_email }}</div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ fmtDate(b.requested_date) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ b.guests_count }}</td>
                <td class="px-4 py-3">
                  <AppBadge variant="info">{{ sourceLabels[b.source] ?? b.source }}</AppBadge>
                </td>
                <td class="px-4 py-3">
                  <AppBadge :variant="bookingStatusConfig[b.status]?.variant ?? 'neutral'">
                    {{ bookingStatusConfig[b.status]?.label ?? b.status }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3">
                  <div class="flex gap-2">
                    <button v-if="b.status === 'pending'" @click="confirmBooking(b)"
                      class="text-xs text-green-600 hover:underline font-semibold">✅ تأكيد</button>
                    <button v-if="b.status === 'pending' || b.status === 'confirmed'" @click="cancelBooking(b)"
                      class="text-xs text-red-500 hover:underline">إلغاء</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ TAB: OFFERS ══ -->
    <div v-else-if="tab === 'offers'" class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input type="checkbox" v-model="offerActiveOnly" @change="loadOffers" class="rounded" />
            النشطة فقط
          </label>
          <span class="text-sm text-gray-500 dark:text-gray-500">{{ offers.length }} عرض</span>
        </div>
        <AppButton size="sm" @click="openCreateOffer">+ إضافة عرض</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <EmptyState v-if="!offers.length" icon="🎁" title="لا توجد عروض" class="col-span-full" />
        <AppCard v-for="o in offers" :key="o.id" padding="md">
          <div class="flex items-start justify-between mb-2">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ o.title }}</div>
              <div v-if="o.title_ar" class="text-xs text-gray-500 dark:text-gray-500">{{ o.title_ar }}</div>
            </div>
            <div class="flex gap-1">
              <AppBadge :variant="isOfferActive(o) ? 'success' : 'neutral'">
                {{ isOfferActive(o) ? 'نشط' : 'منتهٍ' }}
              </AppBadge>
              <AppBadge variant="info">{{ offerTypeLabels[o.offer_type] ?? o.offer_type }}</AppBadge>
            </div>
          </div>
          <div class="flex items-center gap-2 mt-3">
            <span class="text-gray-400 dark:text-gray-500 line-through text-sm">{{ fmtMoney(o.original_price) }} ج</span>
            <span class="text-lg font-black text-green-600">{{ fmtMoney(o.offer_price) }} ج</span>
          </div>
          <div class="text-xs text-gray-500 dark:text-gray-500 mt-1">{{ fmtDate(o.valid_from) }} → {{ fmtDate(o.valid_until) }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">
            {{ o.bookings_count }} حجز
            {{ o.max_bookings > 0 ? `/ ${o.max_bookings}` : '' }}
          </div>
          <button @click="openEditOffer(o)" class="mt-3 text-sm text-blue-600 hover:underline">✏️ تعديل</button>
        </AppCard>
      </div>
    </div>

    <!-- ══ TAB: PAGES ══ -->
    <div v-else-if="tab === 'pages'" class="space-y-4">
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-500 dark:text-gray-500">{{ pages.length }} صفحة</span>
        <AppButton size="sm" @click="openCreatePage">+ إضافة صفحة</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <EmptyState v-if="!pages.length" icon="📄" title="لا توجد صفحات" subtitle="أنشئ أولى صفحات الموقع" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">العنوان</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الـ Slug</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">النوع</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">آخر تعديل</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in pages" :key="p.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3">
                  <div class="font-semibold text-sm text-gray-900 dark:text-gray-100">{{ p.title }}</div>
                  <div v-if="p.title_ar" class="text-xs text-gray-500 dark:text-gray-500">{{ p.title_ar }}</div>
                </td>
                <td class="px-4 py-3 font-mono text-xs text-gray-600 dark:text-gray-500">/{{ p.slug }}</td>
                <td class="px-4 py-3"><AppBadge variant="info">{{ pageTypeLabels[p.page_type] ?? p.page_type }}</AppBadge></td>
                <td class="px-4 py-3">
                  <AppBadge :variant="p.is_published ? 'success' : 'neutral'">
                    {{ p.is_published ? 'منشور' : 'مسودة' }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-500">{{ fmtDate(p.updated_at) }}</td>
                <td class="px-4 py-3">
                  <div class="flex gap-2">
                    <button @click="openEditPage(p)" class="text-xs text-blue-600 hover:underline">✏️ تعديل</button>
                    <button v-if="auth.hasRole('admin')" @click="deletePage(p)"
                      class="text-xs text-red-500 hover:underline">🗑️ حذف</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ MODAL: OFFER ══ -->
    <AppModal :open="offerModal" @close="offerModal = false" :title="editingOffer ? 'تعديل عرض' : 'إنشاء عرض جديد'">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">العنوان (إنجليزي) *</label>
            <input v-model="offerForm.title" :disabled="!!editingOffer"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">العنوان (عربي)</label>
            <input v-model="offerForm.title_ar" :disabled="!!editingOffer"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
          </div>
          <div v-if="!editingOffer">
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">النوع</label>
            <select v-model="offerForm.offer_type" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              <option v-for="(label, val) in offerTypeLabels" :key="val" :value="val">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">السعر الأصلي *</label>
            <input v-model="offerForm.original_price" type="number" min="0" :disabled="!!editingOffer"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">سعر العرض *</label>
            <input v-model="offerForm.offer_price" type="number" min="0"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div v-if="!editingOffer">
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">من تاريخ</label>
            <input v-model="offerForm.valid_from" type="date" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">حتى تاريخ</label>
            <input v-model="offerForm.valid_until" type="date" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">الحد الأقصى للحجوزات (-1 = غير محدود)</label>
            <input v-model="offerForm.max_bookings" type="number"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">رابط الصورة</label>
          <input v-model="offerForm.image_url" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input type="checkbox" v-model="offerForm.is_active" class="rounded" />
          نشط
        </label>
        <div class="flex gap-3 justify-end pt-2">
          <AppButton variant="ghost" @click="offerModal = false">إلغاء</AppButton>
          <AppButton :loading="savingOffer" @click="saveOffer">{{ editingOffer ? 'تحديث' : 'إنشاء' }}</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ MODAL: PAGE ══ -->
    <AppModal :open="pageModal" @close="pageModal = false" :title="editingPage ? 'تعديل صفحة' : 'إنشاء صفحة جديدة'">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">العنوان *</label>
            <input v-model="pageForm.title" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">العنوان بالعربي</label>
            <input v-model="pageForm.title_ar" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div v-if="!editingPage">
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">الـ Slug * (حروف صغيرة وشرطة)</label>
            <input v-model="pageForm.slug" pattern="[a-z0-9-]+" placeholder="about-us"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono" />
          </div>
          <div v-if="!editingPage">
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">النوع</label>
            <select v-model="pageForm.page_type" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              <option v-for="(label, val) in pageTypeLabels" :key="val" :value="val">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">ترتيب العرض</label>
            <input v-model="pageForm.sort_order" type="number"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">وصف meta (SEO)</label>
          <textarea v-model="pageForm.meta_desc" rows="2"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"></textarea>
        </div>
        <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input type="checkbox" v-model="pageForm.is_published" class="rounded" />
          منشور (مرئي للزوار)
        </label>
        <div class="flex gap-3 justify-end pt-2">
          <AppButton variant="ghost" @click="pageModal = false">إلغاء</AppButton>
          <AppButton :loading="savingPage" @click="savePage">{{ editingPage ? 'تحديث' : 'إنشاء' }}</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ TAB: BLOG ══ -->
    <div v-if="tab === 'blog'" class="space-y-4">
      <div class="flex items-center justify-between">
        <p class="text-sm text-gray-500 dark:text-gray-500">مقالات المدونة المعروضة على الموقع العام.</p>
        <AppButton size="sm" @click="openCreateBlog">+ مقال جديد</AppButton>
      </div>
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <EmptyState v-else-if="!blogPosts.length" icon="✍️" title="لا توجد مقالات بعد" />
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">العنوان</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">Slug</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">تاريخ الإنشاء</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="p in blogPosts" :key="p.id" class="hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3">
                  <div class="font-semibold text-gray-900 dark:text-gray-100">{{ p.title }}</div>
                  <div v-if="p.title_ar" class="text-xs text-gray-400 dark:text-gray-500">{{ p.title_ar }}</div>
                </td>
                <td class="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-500">{{ p.slug }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="p.is_published ? 'success' : 'neutral'">
                    {{ p.is_published ? 'منشور' : 'مسودة' }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-500">{{ fmtDate(p.created_at) }}</td>
                <td class="px-4 py-3">
                  <div class="flex gap-2">
                    <button @click="openEditBlog(p)" class="text-xs font-semibold text-primary-700 hover:underline">تعديل</button>
                    <button @click="deleteBlogPost(p)" class="text-xs font-semibold text-red-500 hover:underline">حذف</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- مودال مقال -->
    <AppModal :open="showBlogModal" :title="editingBlog ? 'تعديل مقال' : 'مقال جديد'" @close="showBlogModal = false">
      <div class="space-y-3">
        <div>
          <label class="block text-xs font-semibold text-gray-600 dark:text-gray-500 mb-1">العنوان (إنجليزي)</label>
          <input v-model="blogForm.title" type="text" placeholder="My Beach Experience"
            class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm outline-none focus:border-primary-500" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-gray-600 dark:text-gray-500 mb-1">العنوان (عربي)</label>
          <input v-model="blogForm.title_ar" type="text" placeholder="تجربتي على الشاطئ"
            class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm outline-none focus:border-primary-500" />
        </div>
        <div v-if="!editingBlog">
          <label class="block text-xs font-semibold text-gray-600 dark:text-gray-500 mb-1">Slug (URL)</label>
          <input v-model="blogForm.slug" type="text" placeholder="my-beach-experience"
            class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm outline-none focus:border-primary-500 font-mono" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-gray-600 dark:text-gray-500 mb-1">مقتطف (اختياري)</label>
          <textarea v-model="blogForm.excerpt" rows="3" placeholder="وصف مختصر..."
            class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm outline-none focus:border-primary-500 resize-none"></textarea>
        </div>
        <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
          <input type="checkbox" v-model="blogForm.is_published" class="rounded" />
          منشور (مرئي على الموقع)
        </label>
        <div class="flex justify-end gap-2 pt-2">
          <AppButton variant="ghost" @click="showBlogModal = false">إلغاء</AppButton>
          <AppButton variant="primary" :loading="savingBlog" @click="saveBlogPost">
            {{ savingBlog ? 'جاري الحفظ...' : (editingBlog ? 'تحديث' : 'نشر') }}
          </AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ TAB: CONTACT ══ -->
    <div v-if="tab === 'contact'" class="space-y-4">
      <div class="flex items-center gap-3">
        <p class="text-sm text-gray-500 dark:text-gray-500">رسائل الزوار الواردة عبر نموذج التواصل.</p>
        <AppBadge v-if="contactUnread > 0" variant="warning" size="sm">{{ contactUnread }} غير مقروء</AppBadge>
      </div>
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <EmptyState v-else-if="!contactMessages.length" icon="📬" title="لا توجد رسائل بعد" />
      <div v-else class="space-y-3">
        <AppCard v-for="m in contactMessages" :key="m.id" padding="md"
          :class="!m.is_read ? 'border-r-4 border-r-amber-400' : ''">
          <div class="flex items-start justify-between gap-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-gray-900 dark:text-gray-100">{{ m.name }}</span>
                <span class="text-xs text-gray-400 dark:text-gray-500">{{ m.email }}</span>
                <span v-if="m.phone" class="text-xs text-gray-400 dark:text-gray-500">{{ m.phone }}</span>
                <AppBadge v-if="!m.is_read" size="sm" variant="warning">جديد</AppBadge>
              </div>
              <div v-if="m.subject" class="text-sm font-semibold text-gray-700 dark:text-gray-300 mt-1">{{ m.subject }}</div>
              <p class="text-sm text-gray-600 dark:text-gray-500 mt-1 line-clamp-3">{{ m.message }}</p>
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-500 shrink-0">{{ fmtDate(m.created_at) }}</div>
          </div>
        </AppCard>
      </div>
    </div>

  </div>
</template>

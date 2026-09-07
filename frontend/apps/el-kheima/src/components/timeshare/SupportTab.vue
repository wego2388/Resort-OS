<script setup lang="ts">
// خدمة عملاء الملكية الجزئية المستقلة (تذاكر دعم) — استُخرج من
// TimeshareView.vue (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, EmptyState, LoadingState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()
const emit = defineEmits<{ changed: [] }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface TicketReply { id: number; author_type: string; message: string; created_at: string }
interface SupportTicket {
  id: number; contract_id: number; subject: string; status: string
  customer_name?: string; contract_number?: string
  replies: TicketReply[]
}

const toast = useToast()
const { t } = useI18n()
const branchId = computed(() => props.branchId)

const supportTickets = ref<SupportTicket[]>([])
const ticketsLoading = ref(false)
const ticketsStatus = ref('open')
const ticketModal = ref({ open: false, ticket: null as SupportTicket | null, reply: '', sending: false })

async function loadSupportTickets() {
  ticketsLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/support-tickets', { params: { branch_id: branchId.value, status: ticketsStatus.value || undefined } })
    supportTickets.value = r.data
  } catch { toast.error(t('backoffice.timeshare.msg.loadTicketsError')) } finally { ticketsLoading.value = false }
}

function openTicketModal(tk: SupportTicket) {
  ticketModal.value = { open: true, ticket: tk, reply: '', sending: false }
}
async function sendTicketReply() {
  if (!ticketModal.value.ticket || !ticketModal.value.reply.trim()) return
  ticketModal.value.sending = true
  try {
    const r = await api.post(`/api/v1/timeshare/support-tickets/${ticketModal.value.ticket.id}/reply`, { message: ticketModal.value.reply.trim() })
    ticketModal.value.ticket = r.data
    const idx = supportTickets.value.findIndex(x => x.id === r.data.id)
    if (idx !== -1) supportTickets.value[idx] = r.data
    ticketModal.value.reply = ''
  } catch (e) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.replyError')) }
  finally { ticketModal.value.sending = false }
}
async function updateTicketStatus(tk: SupportTicket, status: string) {
  try {
    const r = await api.patch(`/api/v1/timeshare/support-tickets/${tk.id}`, { status })
    const idx = supportTickets.value.findIndex(x => x.id === tk.id)
    if (idx !== -1) supportTickets.value[idx] = r.data
    if (ticketModal.value.ticket?.id === tk.id) ticketModal.value.ticket = r.data
    toast.success(t('backoffice.timeshare.msg.ticketStatusUpdated'))
    emit('changed')
  } catch (e) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.ticketStatusError')) }
}

onMounted(loadSupportTickets)
</script>

<template>
  <div class="space-y-4">
    <select v-model="ticketsStatus" @change="loadSupportTickets" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
      <option value="open">🟡 {{ t('backoffice.timeshare.ticketStatus.open') }}</option>
      <option value="in_progress">🔵 {{ t('backoffice.timeshare.ticketStatus.in_progress') }}</option>
      <option value="resolved">✅ {{ t('backoffice.timeshare.ticketStatus.resolved') }}</option>
      <option value="closed">⚪ {{ t('backoffice.timeshare.ticketStatus.closed') }}</option>
      <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option>
    </select>

    <LoadingState v-if="ticketsLoading" :label="t('backoffice.timeshare.loadingTickets')" />
    <AppCard v-else padding="none">
      <EmptyState v-if="!supportTickets.length" icon="💬" :title="t('backoffice.timeshare.noResults')" />
      <div v-else class="divide-y divide-stone-100 dark:divide-border">
        <button v-for="tk in supportTickets" :key="tk.id" type="button" @click="openTicketModal(tk)"
          class="w-full text-start p-4 flex items-center justify-between gap-3 hover:bg-stone-50 dark:hover:bg-gray-800/40">
          <div>
            <div class="font-bold text-gray-900 dark:text-gray-100">{{ tk.subject }}</div>
            <div class="text-sm text-gray-600 dark:text-gray-300">{{ tk.customer_name }} — {{ tk.contract_number }}</div>
          </div>
          <AppBadge size="sm" :variant="tk.status === 'open' ? 'warning' : tk.status === 'resolved' || tk.status === 'closed' ? 'success' : 'info'">{{ t(`backoffice.timeshare.ticketStatus.${tk.status}`) }}</AppBadge>
        </button>
      </div>
    </AppCard>

    <!-- ══ SUPPORT TICKET MODAL ══ -->
    <AppModal :open="ticketModal.open" :title="ticketModal.ticket?.subject ?? ''" size="md" @close="ticketModal.open = false">
      <div v-if="ticketModal.ticket" class="space-y-4">
        <div class="flex items-center gap-2">
          <select :value="ticketModal.ticket.status" @change="updateTicketStatus(ticketModal.ticket, ($event.target as HTMLSelectElement).value)"
            class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
            <option value="open">🟡 {{ t('backoffice.timeshare.ticketStatus.open') }}</option>
            <option value="in_progress">🔵 {{ t('backoffice.timeshare.ticketStatus.in_progress') }}</option>
            <option value="resolved">✅ {{ t('backoffice.timeshare.ticketStatus.resolved') }}</option>
            <option value="closed">⚪ {{ t('backoffice.timeshare.ticketStatus.closed') }}</option>
          </select>
        </div>
        <div class="space-y-2 max-h-72 overflow-y-auto">
          <div v-for="rep in ticketModal.ticket.replies" :key="rep.id"
            :class="['max-w-[80%] rounded-2xl px-4 py-2 text-sm', rep.author_type === 'owner' ? 'bg-stone-100 dark:bg-gray-800' : 'bg-blue-50 dark:bg-blue-950/40 ms-auto']">
            <div class="text-xs font-bold text-gray-500 dark:text-gray-400 mb-1">{{ rep.author_type === 'owner' ? t('backoffice.timeshare.ticketFromOwner') : t('backoffice.timeshare.ticketFromStaff') }}</div>
            {{ rep.message }}
          </div>
        </div>
        <div v-if="ticketModal.ticket.status !== 'closed'" class="flex gap-2">
          <textarea v-model="ticketModal.reply" rows="2" :placeholder="t('backoffice.timeshare.ticketReplyPlaceholder')"
            class="flex-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm resize-none" />
          <AppButton :disabled="ticketModal.sending || !ticketModal.reply.trim()" @click="sendTicketReply">{{ t('backoffice.timeshare.send') }}</AppButton>
        </div>
      </div>
    </AppModal>
  </div>
</template>

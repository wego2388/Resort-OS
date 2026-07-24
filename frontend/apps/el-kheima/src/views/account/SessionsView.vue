<script setup lang="ts">
/**
 * SessionsView — Gate 2B3B session & security self-service (Slice 3 UI).
 *
 * Available to ANY authenticated user. Lists the user's OWN active sessions
 * (GET /auth/sessions) with the ability to revoke a single session or every
 * OTHER session, and shows their recent security activity
 * (GET /auth/security-activity, paginated).
 *
 * Revocation is a sensitive action: it always goes through StepUpConfirmModal
 * (reuse — NOT a parallel confirm), which performs the step-up handshake and
 * hands back a one-time `X-Step-Up-Token`. These two intents are reasonless
 * (`extra="forbid"` server-side), so the modal is opened with
 * `:require-reason="false"`. On a 403 STEP_UP_INVALID from the retried
 * mutation we feed a fresh `error-message` back into the modal (it resets and
 * asks again) — never an automatic resend, mirroring SettingsView.vue.
 *
 * No step-up token or any secret is ever written to localStorage/sessionStorage.
 * Direction is inherited from the app root — this screen never forces dir.
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppButton, AppBadge, AppSpinner, EmptyState, Paginator, useToast } from '@resort-os/ui'
import LanguageSwitcher from '../../components/LanguageSwitcher.vue'
import StepUpConfirmModal from '../../components/StepUpConfirmModal.vue'

const { t, te } = useI18n()
const { formatDateTime } = useStaffFormat()
const toast = useToast()
const router = useRouter()

// ── Active sessions ─────────────────────────────────────────────────────────
interface SessionRow {
  session_ref: string
  started_at: string
  last_active_at: string
  expires_at: string
  device: string | null
  current: boolean
}

const sessions = ref<SessionRow[]>([])
const sessionsLoading = ref(true)
const sessionsError = ref('')

const currentSession = computed(() => sessions.value.find((s) => s.current) ?? null)
const otherSessions = computed(() => sessions.value.filter((s) => !s.current))

async function loadSessions() {
  sessionsLoading.value = true
  sessionsError.value = ''
  try {
    const res = await api.get(ENDPOINTS.auth.sessions)
    sessions.value = res.data.sessions ?? []
  } catch {
    sessionsError.value = t('account.sessions.loadError')
  } finally {
    sessionsLoading.value = false
  }
}

// ── Security activity (paginated, limit 20) ─────────────────────────────────
interface ActivityRow {
  id: number
  action: string
  at: string
  ip_address: string | null
  device: string | null
  request_id: string | null
}

const PAGE_SIZE = 20
const activity = ref<ActivityRow[]>([])
const activityTotal = ref(0)
const activityOffset = ref(0)
const activityLoading = ref(true)
const activityError = ref('')

const activityPage = computed(() => Math.floor(activityOffset.value / PAGE_SIZE) + 1)
const activityTotalPages = computed(() => Math.max(1, Math.ceil(activityTotal.value / PAGE_SIZE)))

async function loadActivity() {
  activityLoading.value = true
  activityError.value = ''
  try {
    const res = await api.get(ENDPOINTS.auth.securityActivity, {
      params: { limit: PAGE_SIZE, offset: activityOffset.value },
    })
    activity.value = res.data.items ?? []
    activityTotal.value = res.data.total ?? 0
  } catch {
    activityError.value = t('account.securityActivity.loadError')
  } finally {
    activityLoading.value = false
  }
}

function goToActivityPage(page: number) {
  activityOffset.value = (page - 1) * PAGE_SIZE
  loadActivity()
}

// Known action codes get a friendly bilingual label; anything else shows raw.
function actionLabel(action: string): string {
  const key = `account.securityActivity.actions.${action}`
  return te(key) ? t(key) : action
}

// Formatting is centralized in @resort-os/core's useStaffFormat (locale-aware,
// tabular Latin digits, timezone-safe) — see formatDateTime above.

function deviceLabel(device: string | null): string {
  return device && device.trim() ? device : t('account.sessions.unknownDevice')
}

// ── Step-up-gated revocation ────────────────────────────────────────────────
interface PendingRevoke {
  kind: 'session' | 'others'
  // For 'session' this is the target session_ref; for 'others' it's the
  // keep_session_ref (the current session that must survive).
  sessionRef: string
}

const pendingRevoke = ref<PendingRevoke | null>(null)
const stepUpError = ref('')
const stepUpBusy = ref(false)

const stepUpPurpose = computed<'session_revoke' | 'other_sessions_revoke'>(() =>
  pendingRevoke.value?.kind === 'others' ? 'other_sessions_revoke' : 'session_revoke',
)
const stepUpIntent = computed<Record<string, unknown>>(() => {
  const pending = pendingRevoke.value
  if (!pending) return {}
  return pending.kind === 'others'
    ? { keep_session_ref: pending.sessionRef }
    : { session_ref: pending.sessionRef }
})
const stepUpDescription = computed(() =>
  pendingRevoke.value?.kind === 'others'
    ? t('account.sessions.revokeOthersDescription')
    : t('account.sessions.revokeDescription'),
)

function requestRevokeSession(row: SessionRow) {
  stepUpError.value = ''
  pendingRevoke.value = { kind: 'session', sessionRef: row.session_ref }
}

function requestRevokeOthers() {
  const current = currentSession.value
  if (!current) return
  stepUpError.value = ''
  pendingRevoke.value = { kind: 'others', sessionRef: current.session_ref }
}

async function onStepUpConfirmed({ stepUpToken }: { stepUpToken: string; reason: string }) {
  const pending = pendingRevoke.value
  if (!pending) return
  stepUpBusy.value = true
  try {
    if (pending.kind === 'session') {
      await api.delete(`${ENDPOINTS.auth.sessions}/${pending.sessionRef}`, {
        headers: { 'X-Step-Up-Token': stepUpToken },
      })
      toast.success(t('account.sessions.revokeSuccess'))
    } else {
      const res = await api.post(
        ENDPOINTS.auth.sessionsRevokeOthers,
        {},
        { headers: { 'X-Step-Up-Token': stepUpToken }, withCredentials: true },
      )
      toast.success(t('account.sessions.revokeOthersSuccess', { count: res.data.revoked_count ?? 0 }))
    }
    pendingRevoke.value = null
    await loadSessions()
    // Revocation is itself a logged security event — refresh the activity list.
    await loadActivity()
  } catch (e: any) {
    const code = e?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') {
      // Proof expired/replayed: start a fresh confirmation cycle, never resend.
      stepUpError.value = t('backoffice.stepUp.errorInvalidRestart')
    } else if (code === 'SESSION_NOT_FOUND') {
      toast.error(t('account.sessions.errorNotFound'))
      pendingRevoke.value = null
      await loadSessions()
    } else if (code === 'NO_CURRENT_SESSION') {
      toast.error(t('account.sessions.errorNoCurrent'))
      pendingRevoke.value = null
    } else {
      toast.error(e?.response?.data?.detail?.message ?? t('account.sessions.errorGeneric'))
      pendingRevoke.value = null
    }
  } finally {
    stepUpBusy.value = false
  }
}

function cancelStepUp() {
  pendingRevoke.value = null
  stepUpError.value = ''
}

import { useSmartBack } from '../../composables/useSmartBack'

const { goBack } = useSmartBack('/portal/profile')

onMounted(() => {
  loadSessions()
  loadActivity()
})
</script>

<template>
  <main class="min-h-screen bg-stone-50 dark:bg-gray-950 p-4 sm:p-6">
    <section class="w-full max-w-3xl mx-auto space-y-5">
      <!-- Header -->
      <div class="flex justify-between items-start gap-4">
        <div>
          <h1 class="text-2xl font-black text-gray-800 dark:text-gray-100">{{ t('account.sessions.title') }}</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t('account.sessions.subtitle') }}</p>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <LanguageSwitcher variant="compact" />
          <button
            type="button"
            class="text-sm font-semibold text-gray-600 dark:text-gray-300 border border-stone-200 dark:border-border rounded-lg px-3 py-2 hover:bg-stone-100 dark:hover:bg-gray-800 transition-colors"
            @click="goBack"
          >
            {{ t('account.sessions.back') }}
          </button>
        </div>
      </div>

      <!-- Active sessions -->
      <AppCard :title="t('account.sessions.activeSessionsTitle')">
        <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">{{ t('account.sessions.activeSessionsSubtitle') }}</p>

        <div class="mb-4">
          <AppButton
            v-if="currentSession"
            variant="danger"
            size="sm"
            :disabled="otherSessions.length === 0 || stepUpBusy"
            @click="requestRevokeOthers"
          >
            {{ t('account.sessions.revokeOthers') }}
          </AppButton>
          <p v-else class="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2">
            ⚠️ {{ t('account.sessions.noCurrentSessionNote') }}
          </p>
          <p v-if="currentSession && otherSessions.length === 0" class="text-xs text-gray-400 dark:text-gray-400 mt-1">
            {{ t('account.sessions.noOtherSessions') }}
          </p>
        </div>

        <div v-if="sessionsLoading" class="py-10 flex flex-col items-center gap-3 text-gray-400 dark:text-gray-400">
          <AppSpinner size="lg" />
          <p class="text-sm">{{ t('account.sessions.loading') }}</p>
        </div>

        <div
          v-else-if="sessionsError"
          role="alert"
          aria-live="assertive"
          class="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300"
        >
          <span>⚠️ {{ sessionsError }}</span>
          <button type="button" class="font-semibold underline hover:no-underline" @click="loadSessions">
            {{ t('account.sessions.retry') }}
          </button>
        </div>

        <EmptyState
          v-else-if="sessions.length === 0"
          icon="💻"
          :title="t('account.sessions.empty')"
        />

        <ul v-else class="space-y-3">
          <li
            v-for="s in sessions"
            :key="s.session_ref"
            class="rounded-xl border border-stone-200 dark:border-border p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
          >
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-semibold text-gray-800 dark:text-gray-100 truncate">{{ deviceLabel(s.device) }}</span>
                <AppBadge v-if="s.current" size="sm" variant="success">{{ t('account.sessions.thisDevice') }}</AppBadge>
              </div>
              <dl class="mt-1.5 grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                <div>
                  <dt class="inline font-medium">{{ t('account.sessions.startedAt') }}:</dt>
                  <dd class="inline"> {{ formatDateTime(s.started_at) }}</dd>
                </div>
                <div>
                  <dt class="inline font-medium">{{ t('account.sessions.lastActiveAt') }}:</dt>
                  <dd class="inline"> {{ formatDateTime(s.last_active_at) }}</dd>
                </div>
                <div>
                  <dt class="inline font-medium">{{ t('account.sessions.expiresAt') }}:</dt>
                  <dd class="inline"> {{ formatDateTime(s.expires_at) }}</dd>
                </div>
              </dl>
            </div>
            <div class="flex-shrink-0">
              <AppButton
                v-if="!s.current"
                variant="danger"
                size="sm"
                :disabled="stepUpBusy"
                :aria-label="t('account.sessions.revokeAriaLabel')"
                @click="requestRevokeSession(s)"
              >
                {{ t('account.sessions.revoke') }}
              </AppButton>
            </div>
          </li>
        </ul>
      </AppCard>

      <!-- Security activity -->
      <AppCard :title="t('account.securityActivity.title')">
        <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">{{ t('account.securityActivity.subtitle') }}</p>

        <div v-if="activityLoading" class="py-10 flex flex-col items-center gap-3 text-gray-400 dark:text-gray-400">
          <AppSpinner size="lg" />
          <p class="text-sm">{{ t('account.securityActivity.loading') }}</p>
        </div>

        <div
          v-else-if="activityError"
          role="alert"
          aria-live="assertive"
          class="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300"
        >
          <span>⚠️ {{ activityError }}</span>
          <button type="button" class="font-semibold underline hover:no-underline" @click="loadActivity">
            {{ t('account.sessions.retry') }}
          </button>
        </div>

        <EmptyState
          v-else-if="activity.length === 0"
          icon="🛡️"
          :title="t('account.securityActivity.empty')"
        />

        <template v-else>
          <ul class="space-y-2">
            <li
              v-for="event in activity"
              :key="event.id"
              class="rounded-lg border border-stone-100 dark:border-border/50 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1"
            >
              <div class="min-w-0">
                <span class="font-medium text-gray-800 dark:text-gray-100">{{ actionLabel(event.action) }}</span>
                <div class="text-xs text-gray-400 dark:text-gray-400 mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                  <span v-if="event.ip_address">{{ t('account.securityActivity.ipLabel') }}: {{ event.ip_address }}</span>
                  <span v-if="event.device">{{ t('account.securityActivity.deviceLabel') }}: {{ event.device }}</span>
                </div>
              </div>
              <span class="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">{{ formatDateTime(event.at) }}</span>
            </li>
          </ul>

          <div v-if="activityTotalPages > 1" class="mt-4">
            <Paginator
              :page="activityPage"
              :total-pages="activityTotalPages"
              :total-items="activityTotal"
              :page-size="PAGE_SIZE"
              @update:page="goToActivityPage"
            />
          </div>
        </template>
      </AppCard>
    </section>

    <StepUpConfirmModal
      v-if="pendingRevoke"
      :purpose="stepUpPurpose"
      :intent="stepUpIntent"
      :description="stepUpDescription"
      :require-reason="false"
      :loading="stepUpBusy"
      :error-message="stepUpError"
      @confirmed="onStepUpConfirmed"
      @cancel="cancelStepUp"
    />
  </main>
</template>

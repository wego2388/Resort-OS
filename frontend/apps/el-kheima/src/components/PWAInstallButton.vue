<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AppIcon } from '@resort-os/ui'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

const { t } = useI18n()
const installPrompt = ref<BeforeInstallPromptEvent | null>(null)
const installed = ref(false)

function refreshInstalledState() {
  installed.value = window.matchMedia?.('(display-mode: standalone)').matches ?? false
}

function captureInstallPrompt(event: Event) {
  event.preventDefault()
  installPrompt.value = event as BeforeInstallPromptEvent
}

function markInstalled() {
  installed.value = true
  installPrompt.value = null
}

async function install() {
  const prompt = installPrompt.value
  if (!prompt) return
  await prompt.prompt()
  const choice = await prompt.userChoice
  if (choice.outcome === 'accepted') markInstalled()
}

onMounted(() => {
  refreshInstalledState()
  window.addEventListener('beforeinstallprompt', captureInstallPrompt)
  window.addEventListener('appinstalled', markInstalled)
})
onUnmounted(() => {
  window.removeEventListener('beforeinstallprompt', captureInstallPrompt)
  window.removeEventListener('appinstalled', markInstalled)
})
</script>

<template>
  <button
    v-if="installPrompt && !installed"
    type="button"
    class="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-800 transition-colors hover:bg-primary-100 active:scale-[0.98] dark:bg-primary-950/40 dark:text-primary-300"
    :aria-label="t('backoffice.layout.installApp')"
    :title="t('backoffice.layout.installApp')"
    @click="install"
  >
    <AppIcon name="download" />
  </button>
</template>

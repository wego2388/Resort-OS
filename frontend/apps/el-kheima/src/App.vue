<script setup lang="ts">
// App root — @resort-os/core's useAuthStore boots in main.ts before the
// router's first navigation resolves; router guard handles redirects.
// ToastContainer is mounted here once for the whole app — the shared
// @resort-os/ui LoginView (and any view) calls useToast() to surface errors;
// none of the former 6 apps ever mounted it, so toast.error()/success() calls
// were silently swallowed before this.
import { ToastContainer, ConfirmDialogContainer } from '@resort-os/ui'
import { useStaffLocaleSync } from './composables/useStaffLocaleSync'

// Gate 3A — keep the UI language reconciled to the signed-in user's saved
// preferred_language on login / refresh / PIN switch (shared-terminal safety).
useStaffLocaleSync()
</script>

<template>
  <RouterView />
  <ToastContainer />
  <ConfirmDialogContainer />
</template>

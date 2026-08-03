<script setup lang="ts">
// هوية الضيف عند فتح طاولة جديدة (2026-08-03، طلب Mohamed) — بالظبط نفس
// فكرة شاشة ترحيب الضيف عبر QR (اسم إجباري، تليفون اختياري)، بس هنا
// للحالة اللي الضيف ماصورش QR خالص (الكاشير بيفتحله الطاولة يدويًا).
// بيتنادى بس من startTableOrder في UnifiedPOSView.vue، ولطاولة فاضية
// (مفيش active_order_id) — مش لطاولة مشغولة أصلاً (فيها هوية محفوظة
// بالفعل على الطلب النشط نفسه).
//
// حقل التليفون هنا AppInput نص حر عادي، مش PhoneInput المتخصص — عمدًا،
// عشان يطابق نفس شكل تخزين guest_phone من مسار الضيف عبر QR بالظبط
// (نص خام زي ما اتكتب، مثال "01099998888")؛ PhoneInput بيخزّن 10 أرقام
// محلية بدون الصفر الأول، فاستخدامه هنا كان هيخلق تنسيقين مختلفين لنفس
// العمود (guest_phone) حسب مين كتب الرقم.
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AppButton, AppInput, AppModal } from '@resort-os/ui'

const props = defineProps<{ open: boolean; tableNumber: string }>()
const emit = defineEmits<{
  close: []
  confirm: [{ name: string; phone: string | undefined }]
}>()

const { t } = useI18n()
const name = ref('')
const phone = ref('')

watch(() => props.open, (open) => {
  if (!open) return
  name.value = ''
  phone.value = ''
})

function submit() {
  const trimmedName = name.value.trim()
  if (!trimmedName) return
  emit('confirm', { name: trimmedName, phone: phone.value.trim() || undefined })
}
</script>

<template>
  <AppModal
    :open="open"
    :title="t('backoffice.pos.guestIdentity.title', { table: tableNumber })"
    size="sm"
    :close-label="t('backoffice.pos.close')"
    @close="emit('close')"
  >
    <form class="space-y-4" @submit.prevent="submit">
      <AppInput
        v-model="name"
        :label="t('backoffice.pos.guestIdentity.nameLabel')"
        :placeholder="t('backoffice.pos.guestIdentity.namePlaceholder')"
        required
        autofocus
        autocomplete="name"
      />
      <AppInput
        v-model="phone"
        type="tel"
        inputmode="tel"
        :label="t('backoffice.pos.guestIdentity.phoneLabel')"
        placeholder="01xxxxxxxxx"
        autocomplete="tel"
      />
    </form>

    <template #footer>
      <div class="flex items-center justify-end gap-2">
        <AppButton variant="outline" @click="emit('close')">
          {{ t('backoffice.pos.close') }}
        </AppButton>
        <AppButton variant="primary" :disabled="!name.trim()" @click="submit">
          {{ t('backoffice.pos.guestIdentity.confirm') }}
        </AppButton>
      </div>
    </template>
  </AppModal>
</template>

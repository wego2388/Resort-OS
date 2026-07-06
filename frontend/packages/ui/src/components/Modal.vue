<script setup lang="ts">
withDefaults(defineProps<{
  open: boolean
  title?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  // ⚠️ باج حقيقي اتكشف حي (2026-07-06، اختبار زر "📨 استبيان الرضا" في
  // TimeshareView كمدير): useConfirm() بيفتح AppModal تاني فوق أي AppModal
  // شاشة مفتوحة أصلاً (نفس المكوّن، الاتنين Teleport لـ body بنفس z-50).
  // ترتيب عناصر body بيتحدد بترتيب أول mount لكل Teleport instance، مش
  // بترتيب ظهور المحتوى — وConfirmDialogContainer بيتحمّل مرة واحدة بدري
  // جدًا في App.vue، يعني أي مودال شاشة بيتفتح بعده (زي بروفايل عميل
  // التايم شير) بيطلع فوقه فعليًا في الـ DOM رغم تساوي z-index. النتيجة:
  // زر تأكيد حقيقي ("نعم، أرسل") كان مقفول خلف مودال الشاشة، غير قابل
  // للضغط عليه خالص — أي useConfirm() جوه أي مودال مفتوح في المشروع كله
  // كان معطّل عمليًا. الحل: z-index قابل للتحديد، ConfirmDialogContainer
  // بيطلب طبقة أعلى صراحة عشان يفضل دايمًا فوق أي مودال محتوى.
  zIndex?: string
}>(), { zIndex: 'z-50' })
const emit = defineEmits<{ close: [] }>()
</script>
<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" :class="['fixed inset-0 flex items-center justify-center p-4', zIndex]" @click.self="emit('close')">
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="emit('close')" />
        <div :class="[
          'relative bg-white rounded-2xl shadow-2xl w-full max-h-[90vh] flex flex-col',
          size === 'sm' ? 'max-w-sm'  : '',
          size === 'lg' ? 'max-w-2xl' : '',
          size === 'xl' ? 'max-w-4xl' : '',
          (!size || size === 'md') ? 'max-w-lg' : '',
        ]">
          <div v-if="title" class="flex items-center justify-between px-6 py-4 border-b border-stone-100 flex-shrink-0">
            <h2 class="text-lg font-bold text-gray-900">{{ title }}</h2>
            <button @click="emit('close')" class="p-1 rounded-lg hover:bg-gray-100 transition-colors">
              <svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
          <div class="overflow-y-auto flex-1 p-6">
            <slot />
          </div>
          <div v-if="$slots.footer" class="px-6 py-4 border-t border-stone-100 flex-shrink-0">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
<style scoped>
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>

<script setup lang="ts">
import { AppIcon, type IconName } from '@resort-os/ui'

const destinations: ReadonlyArray<{
  to: string
  title: string
  subtitle: string
  icon: IconName
}> = [
  {
    to: '/shifts',
    title: 'الورديات',
    subtitle: 'متابعة الورديات المفتوحة والفروقات وسجل الإغلاق',
    icon: 'bell',
  },
  {
    to: '/hr',
    title: 'الموظفون',
    subtitle: 'ملخص الرواتب والحضور وحالة فريق العمل',
    icon: 'users',
  },
  {
    to: '/mall',
    title: 'المول التجاري',
    subtitle: 'العقود والتحصيل والمتأخرات وجاهزية سجل الوحدات',
    icon: 'building',
  },
  {
    to: '/documents',
    title: 'المستندات',
    subtitle: 'التراخيص والعقود التي أتاحت الإدارة عرضها لك',
    icon: 'archive',
  },
]
</script>

<template>
  <div class="flex-1 overflow-y-auto overscroll-contain p-4">
    <section aria-labelledby="more-title" class="mx-auto max-w-3xl space-y-4">
      <div>
        <h2 id="more-title" class="text-xl font-black text-owner-text">المزيد</h2>
        <p class="mt-1 text-sm text-owner-muted">وصول منظم للتفاصيل التشغيلية الأقل استخدامًا.</p>
      </div>

      <div class="grid gap-3 sm:grid-cols-2">
        <RouterLink
          v-for="destination in destinations"
          :key="destination.to"
          :to="destination.to"
          class="owner-card flex min-h-24 items-center gap-4 text-start transition-colors active:border-owner-green"
        >
          <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-owner-green/10 text-owner-green">
            <AppIcon :name="destination.icon" size="lg" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block font-bold text-owner-text">{{ destination.title }}</span>
            <span class="mt-1 block text-xs leading-5 text-owner-muted">{{ destination.subtitle }}</span>
          </span>
          <AppIcon name="chevron-left" class="text-owner-muted" />
        </RouterLink>
      </div>
    </section>
  </div>
</template>

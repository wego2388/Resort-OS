/**
 * Marketing-copy messages for the public guest website (apps/public only).
 *
 * These are merged into the shared `@resort-os/core/i18n` instance at app
 * bootstrap time (see main.ts) via `i18n.global.mergeLocaleMessage()`, under
 * the `marketing` namespace — so they never collide with the staff/QR/kitchen
 * keys already shipped in `packages/core/src/i18n/locales/*.json`, and they
 * never bloat the bundle of the `qr`/`el-kheima` apps (this file only gets
 * imported here, in `apps/public`).
 *
 * Content source: real brand material mined from
 * /home/wego/projects/elkheima-beach-resort-marketing/ (01_brand, 05_content) —
 * NOT invented placeholder copy. Arabic + English are sourced directly from
 * that repo (BRAND_GUIDE.md, VISUAL_IDENTITY_GUIDE.md, READY_TO_USE_CONTENT.md,
 * MASTER_FILE_COMPLETE.md, CONTACT_INFO_UPDATED.md, contact_info.csv).
 * Russian + Italian are reasonable machine-quality translations of that same
 * source copy — there was no authoritative ru/it source material in the
 * content repo, so treat those two locales as translation-quality, not
 * brand-reviewed copy.
 */

export interface MarketingMessages {
  brand: { name: string; nameNative: string; tagline: string }
  nav: { home: string; rooms: string; dining: string; book: string; contact: string; callUs: string; menuToggle: string; about: string; faq: string }
  hero: {
    eyebrow: string
    title: string
    subtitle: string
    cta: string
    secondaryCta: string
  }
  about: {
    title: string
    body: string
  }
  stats: {
    beachArea: string
    beachAreaLabel: string
    beachLength: string
    beachLengthLabel: string
    totalArea: string
    totalAreaLabel: string
    ranking: string
    rankingLabel: string
  }
  valueProps: {
    title: string
    subtitle: string
    beach: { title: string; desc: string }
    dining: { title: string; desc: string }
    water: { title: string; desc: string }
    rooms: { title: string; desc: string }
    events: { title: string; desc: string }
    families: { title: string; desc: string }
  }
  rooms: {
    title: string
    subtitle: string
    loading: string
    empty: string
    error: string
    perNight: string
    maxGuests: string
    from: string
    bookThis: string
  }
  dining: {
    title: string
    subtitle: string
    outletSubtitle: string
    loading: string
    error: string
    empty: string
  }
  cta: {
    title: string
    subtitle: string
    button: string
  }
  contact: {
    title: string
    phone: string
    address: string
    hours: string
    hoursValue: string
    follow: string
  }
  footer: {
    rights: string
    privacyLink: string
    termsLink: string
  }
  // Batch 2 (Public Phase 0 migration, 2026-07-21) — About/Contact/FAQ/
  // Privacy/Terms, the routes that didn't exist at all before this batch
  // (confirmed via router/index.ts — only /, /dining, /book, /confirmation
  // existed). Privacy/Terms/FAQ ship as real page shells with an explicit
  // "content pending" notice rather than fabricated legal/FAQ text —
  // Mohamed asked to write that content himself later (2026-07-21).
  pages: {
    about: { subtitle: string }
    contact: {
      title: string; subtitle: string; formTitle: string
      fullName: string; fullNamePlaceholder: string
      email: string; phone: string
      subject: string; subjectPlaceholder: string
      message: string; messagePlaceholder: string
      submit: string; submitting: string
      validationError: string; genericError: string
      successTitle: string; successBody: string
      infoTitle: string
    }
    faq: { title: string; subtitle: string; pendingNotice: string }
    privacy: { title: string; pendingNotice: string }
    terms: { title: string; pendingNotice: string }
  }
  booking: {
    back: string
    title: string
    subtitle: string
    fullName: string
    fullNamePlaceholder: string
    phone: string
    email: string
    checkIn: string
    checkOut: string
    adults: string
    children: string
    roomType: string
    roomTypePlaceholder: string
    specialRequests: string
    specialRequestsPlaceholder: string
    submit: string
    submitting: string
    responseTime: string
    validationError: string
    genericError: string
    roomTypeStandard: string
    roomTypeSeaView: string
    roomTypeSuite: string
    roomTypeChalet: string
    subjectLine: string
  }
  confirmation: {
    title: string
    body: string
    backHome: string
  }
  // Batch 1 (Public Phase 0 migration, 2026-07-21) — page titles for the 3
  // routes that never had one (order/beachCheckin/survey — QR/token guest
  // flows, no nav entry) + a <meta name="description"> per route, read by
  // useSEO.ts. See docs/audits/public-phase-0/07_MIGRATION_BATCH_PROPOSAL.md.
  pageTitles: {
    order: string
    beachCheckin: string
    survey: string
  }
  seo: {
    home: string
    dining: string
    booking: string
    confirmation: string
    order: string
    beachCheckin: string
    survey: string
    about: string
    contact: string
    faq: string
    privacy: string
    terms: string
  }
}

const ar: MarketingMessages = {
  brand: {
    name: 'El Kheima Beach Resort',
    nameNative: 'منتجع الخيمة الشاطئي',
    tagline: 'ملاذك الخاص في انتظارك',
  },
  nav: { home: 'الرئيسية', rooms: 'الغرف', dining: 'المطعم والكافيه', book: 'احجز الآن', contact: 'تواصل معنا', callUs: 'اتصل بنا', menuToggle: 'فتح/إغلاق القائمة', about: 'من نحن', faq: 'الأسئلة الشائعة' },
  hero: {
    eyebrow: 'خليج شرم الماية • شرم الشيخ',
    title: 'منتجع الخيمة الشاطئي',
    subtitle: 'منتجع فاخر على شاطئ البحر الأحمر — حيث تُصنع الذكريات',
    cta: 'احجز الآن',
    secondaryCta: 'استفسر عن الحجز',
  },
  about: {
    title: 'مرحباً بكم في منتجع الخيمة',
    body: 'يقع منتجع الخيمة في خليج شرم المايا الخلاب، ويوفر تجربة لا تُنسى على مساحة 35,000 متر مربع من الواجهة البحرية البكر، بشاطئ رملي خاص وإطلالة بحرية صافية. مصنف كأفضل منتجع شاطئي في المنطقة، نفخر بخدمتنا الاستثنائية ومرافقنا النظيفة وخلق ذكريات تدوم مدى الحياة.',
  },
  stats: {
    beachArea: '13,000 م²', beachAreaLabel: 'شاطئ رملي خاص',
    beachLength: '225 م', beachLengthLabel: 'إطلالة بحرية صافية',
    totalArea: '35,000 م²', totalAreaLabel: 'مساحة المنتجع الكلية',
    ranking: '#1', rankingLabel: 'أفضل منتجع شاطئي في المنطقة',
  },
  valueProps: {
    title: 'ما يميزنا',
    subtitle: 'كل ما تحتاجه لعطلة لا تُنسى في شرم الشيخ',
    beach: { title: 'شاطئ خاص', desc: 'شاطئ رملي خاص بمساحة 13,000 م² وإطلالة بحرية صافية بطول 225 متر، مع كراسي ومظلات وخدمة منقذين' },
    dining: { title: 'مطبخ إيطالي أصيل', desc: 'مطعم إيطالي راقي وكافيه مطل على البحر، وبار للمشروبات والكوكتيلات، وصالة شيشة VIP' },
    water: { title: 'رياضات مائية', desc: 'غطس وطيران شراعي وسباحة ودورات غوص — أنشطة مائية شاملة لكل أفراد العائلة' },
    rooms: { title: 'غرف إطلالة بحرية', desc: 'غرف وأجنحة مطلة على البحر مصممة لراحتك، بجميع وسائل الراحة الحديثة' },
    events: { title: 'مناسبات وأفراح', desc: 'قاعة مخصصة للمناسبات والأفراح والفعاليات الخاصة بإطلالة بحرية ساحرة' },
    families: { title: 'مثالي للعائلات والأزواج', desc: 'أنشطة ترفيهية آمنة للعائلات، وأجواء رومانسية هادئة للأزواج على مدار العام' },
  },
  rooms: {
    title: 'غرفنا وأجنحتنا',
    subtitle: 'اختر الغرفة الأنسب لإقامتك',
    loading: 'جاري تحميل الغرف المتاحة...',
    empty: 'لا توجد غرف متاحة حالياً، يرجى التواصل معنا مباشرة',
    error: 'تعذر تحميل الغرف الآن، يرجى المحاولة لاحقاً',
    perNight: 'لليلة الواحدة',
    maxGuests: 'حتى {n} نزلاء',
    from: 'يبدأ من',
    bookThis: 'احجز هذه الغرفة',
  },
  dining: {
    title: 'قائمة الطعام والمشروبات',
    subtitle: 'تذوق أشهى الأطباق ومشروباتنا المميزة',
    outletSubtitle: 'اكتشف قائمتنا الكاملة',
    loading: 'جاري تحميل القائمة...',
    error: 'تعذر تحميل القائمة الآن، يرجى المحاولة لاحقاً',
    empty: 'القائمة غير متاحة حالياً',
  },
  cta: {
    title: 'ابدأ تجربتك معنا اليوم',
    subtitle: 'أسعار تنافسية وخدمة لا مثيل لها',
    button: 'استفسر عن الحجز',
  },
  contact: {
    title: 'تواصل معنا',
    phone: 'أرقام الحجز والاستفسار',
    address: 'شارع محمد اليماني، خليج شرم الماية، السوق التجاري القديم (بجوار نادي الرياضات البحرية)، شرم الشيخ، جنوب سيناء 46628',
    hours: 'مواعيد العمل',
    hoursValue: 'الاستقبال على مدار الساعة • الشاطئ 8 صباحاً حتى الغروب • المطعم 12 ظهراً حتى 11 مساءً',
    follow: 'تابعنا',
  },
  footer: {
    rights: 'جميع الحقوق محفوظة',
    privacyLink: 'سياسة الخصوصية',
    termsLink: 'الشروط والأحكام',
  },
  booking: {
    back: 'الرئيسية',
    title: 'استفسار حجز',
    subtitle: 'سيتم التواصل معك خلال 24 ساعة',
    fullName: 'الاسم الكامل',
    fullNamePlaceholder: 'محمد أحمد',
    phone: 'رقم الهاتف',
    email: 'البريد الإلكتروني',
    checkIn: 'تاريخ الوصول',
    checkOut: 'تاريخ المغادرة',
    adults: 'البالغون',
    children: 'الأطفال',
    roomType: 'نوع الغرفة',
    roomTypePlaceholder: 'اختر نوع الغرفة',
    specialRequests: 'طلبات خاصة',
    specialRequestsPlaceholder: 'أي طلبات أو ملاحظات...',
    submit: 'إرسال الاستفسار',
    submitting: 'جاري الإرسال...',
    responseTime: 'سيتم التواصل معك خلال 24 ساعة',
    validationError: 'الرجاء ملء الاسم ورقم الهاتف وتاريخ الوصول',
    genericError: 'حدث خطأ، يرجى المحاولة مرة أخرى',
    roomTypeStandard: 'غرفة قياسية',
    roomTypeSeaView: 'غرفة إطلالة بحر',
    roomTypeSuite: 'جناح فاخر',
    roomTypeChalet: 'شاليه خاص',
    subjectLine: 'استفسار حجز',
  },
  confirmation: {
    title: 'تم إرسال طلبك بنجاح!',
    body: 'سيتم التواصل معك قريباً لتأكيد التفاصيل',
    backHome: 'العودة للرئيسية',
  },
  pageTitles: {
    order: 'اطلب الآن',
    beachCheckin: 'تسجيل دخول الشاطئ',
    survey: 'استبيان الرضا',
  },
  seo: {
    home: 'منتجع الخيمة الشاطئي — منتجع خاص على شاطئ خليج شرم الماية، شرم الشيخ. شاطئ رملي خاص 13,000 م²، مطعم إيطالي أصيل، رياضات مائية، وغرف بإطلالة بحرية.',
    dining: 'استكشف قائمة الطعام والمشروبات في منتجع الخيمة — مطبخ إيطالي أصيل، كافيه مطل على البحر، وبار مشروبات وكوكتيلات.',
    booking: 'احجز إقامتك في منتجع الخيمة الشاطئي — غرف وأجنحة بإطلالة بحرية، شرم الشيخ. سيتم التواصل معك خلال 24 ساعة لتأكيد حجزك.',
    confirmation: 'تم استلام طلب حجزك بنجاح في منتجع الخيمة الشاطئي — سيتواصل معك فريقنا قريبًا لتأكيد التفاصيل.',
    order: 'اطلب طعامك ومشروباتك مباشرة من طاولتك في منتجع الخيمة الشاطئي.',
    beachCheckin: 'تسجيل دخول حجز الشاطئ في منتجع الخيمة الشاطئي.',
    survey: 'شاركنا رأيك في تجربتك بمنتجع الخيمة الشاطئي — رضاك يهمنا.',
    about: 'تعرّف على قصة منتجع الخيمة الشاطئي وما يميزنا — شاطئ خاص، مطبخ إيطالي أصيل، ورياضات مائية في شرم الشيخ.',
    contact: 'تواصل مع منتجع الخيمة الشاطئي — أرقام الهاتف، العنوان، ونموذج تواصل مباشر.',
    faq: 'إجابات على أكثر الأسئلة شيوعًا عن الإقامة في منتجع الخيمة الشاطئي.',
    privacy: 'سياسة الخصوصية الخاصة بمنتجع الخيمة الشاطئي.',
    terms: 'الشروط والأحكام الخاصة بمنتجع الخيمة الشاطئي.',
  },
  pages: {
    about: { subtitle: 'قصتنا وما يميزنا' },
    contact: {
      title: 'تواصل معنا',
      subtitle: 'يسعدنا الرد على استفساراتك — راسلنا وسيتواصل معك فريقنا خلال 24 ساعة',
      formTitle: 'أرسل رسالة',
      fullName: 'الاسم الكامل', fullNamePlaceholder: 'محمد أحمد',
      email: 'البريد الإلكتروني', phone: 'رقم الهاتف',
      subject: 'الموضوع', subjectPlaceholder: 'استفسار عام',
      message: 'الرسالة', messagePlaceholder: 'اكتب رسالتك هنا...',
      submit: 'إرسال', submitting: 'جاري الإرسال...',
      validationError: 'الرجاء ملء الاسم والبريد الإلكتروني والرسالة',
      genericError: 'حدث خطأ، يرجى المحاولة مرة أخرى أو التواصل عبر الهاتف',
      successTitle: 'تم إرسال رسالتك بنجاح!', successBody: 'سيتواصل معك فريقنا قريبًا',
      infoTitle: 'بيانات التواصل',
    },
    faq: {
      title: 'الأسئلة الشائعة', subtitle: 'إجابات على أكثر الأسئلة شيوعًا',
      pendingNotice: 'المحتوى قيد الإعداد — لأي استفسار الآن، تواصل معنا مباشرة',
    },
    privacy: {
      title: 'سياسة الخصوصية',
      pendingNotice: 'سيتم نشر سياسة الخصوصية الكاملة قريبًا. لأي استفسار بخصوص بياناتك، تواصل معنا مباشرة.',
    },
    terms: {
      title: 'الشروط والأحكام',
      pendingNotice: 'سيتم نشر الشروط والأحكام الكاملة قريبًا. لأي استفسار، تواصل معنا مباشرة.',
    },
  },
}

const en: MarketingMessages = {
  brand: {
    name: 'El Kheima Beach Resort',
    nameNative: 'El Kheima Beach Resort',
    tagline: 'Your Private Retreat Awaits',
  },
  nav: { home: 'Home', rooms: 'Rooms', dining: 'Dining', book: 'Book Now', contact: 'Contact', callUs: 'Call Us', menuToggle: 'Toggle menu', about: 'About', faq: 'FAQ' },
  hero: {
    eyebrow: 'Sharm El Maya Bay • Sharm El Sheikh',
    title: 'El Kheima Beach Resort',
    subtitle: 'A luxury beachfront resort on the Red Sea — where memories are made',
    cta: 'Book Now',
    secondaryCta: 'Enquire About Booking',
  },
  about: {
    title: 'Welcome to El Kheima Beach Resort',
    body: 'Nestled in the stunning Sharm El Maya Bay, El Kheima Beach Resort offers an unforgettable escape on 35,000 m² of pristine beachfront property, with a private sandy beach and crystal-clear sea views. Ranked #1 beach resort in the area, we pride ourselves on exceptional service, pristine facilities, and creating memories that last a lifetime.',
  },
  stats: {
    beachArea: '13,000 m²', beachAreaLabel: 'Private sandy beach',
    beachLength: '225 m', beachLengthLabel: 'Crystal-clear sea views',
    totalArea: '35,000 m²', totalAreaLabel: 'Total resort area',
    ranking: '#1', rankingLabel: 'Ranked beach resort in the area',
  },
  valueProps: {
    title: 'What Sets Us Apart',
    subtitle: 'Everything you need for an unforgettable getaway in Sharm El Sheikh',
    beach: { title: 'Private Beach', desc: '13,000 m² of private sandy beach with 225 meters of crystal-clear sea views, loungers, umbrellas and lifeguard service' },
    dining: { title: 'Authentic Italian Dining', desc: 'A refined Italian restaurant and beachfront café, a cocktail & drinks bar, and a VIP shisha lounge' },
    water: { title: 'Water Sports', desc: 'Snorkeling, parasailing, swimming and diving courses — full water activities for the whole family' },
    rooms: { title: 'Sea View Rooms', desc: 'Sea-facing rooms and suites designed for your comfort, with all modern amenities' },
    events: { title: 'Events & Weddings', desc: 'A dedicated venue for weddings, celebrations and special events with a stunning sea view' },
    families: { title: 'Perfect for Couples & Families', desc: 'Safe, fun activities for families and a calm, romantic atmosphere for couples, year-round' },
  },
  rooms: {
    title: 'Our Rooms & Suites',
    subtitle: 'Choose the room that fits your stay',
    loading: 'Loading available rooms...',
    empty: 'No rooms available right now — please contact us directly',
    error: 'Could not load rooms right now, please try again later',
    perNight: 'per night',
    maxGuests: 'Up to {n} guests',
    from: 'From',
    bookThis: 'Book This Room',
  },
  dining: {
    title: 'Food & Drinks Menu',
    subtitle: 'Taste our finest dishes and signature drinks',
    outletSubtitle: 'Discover our full menu',
    loading: 'Loading the menu...',
    error: 'Could not load the menu right now, please try again later',
    empty: 'Menu is currently unavailable',
  },
  cta: {
    title: 'Start Your Experience With Us Today',
    subtitle: 'Competitive rates and unmatched service',
    button: 'Enquire About Booking',
  },
  contact: {
    title: 'Get in Touch',
    phone: 'Reservations & Enquiries',
    address: 'Mohamed El Yamany Street, Sharm El Maya Bay, Old Market (Next to the Water Sports Club), Sharm El Sheikh, South Sinai 46628',
    hours: 'Opening Hours',
    hoursValue: 'Reception 24/7 • Beach 8:00 AM – Sunset • Restaurant 12:00 PM – 11:00 PM',
    follow: 'Follow Us',
  },
  footer: {
    rights: 'All rights reserved',
    privacyLink: 'Privacy Policy',
    termsLink: 'Terms & Conditions',
  },
  booking: {
    back: 'Home',
    title: 'Booking Enquiry',
    subtitle: "We'll get back to you within 24 hours",
    fullName: 'Full Name',
    fullNamePlaceholder: 'John Smith',
    phone: 'Phone Number',
    email: 'Email',
    checkIn: 'Check-in Date',
    checkOut: 'Check-out Date',
    adults: 'Adults',
    children: 'Children',
    roomType: 'Room Type',
    roomTypePlaceholder: 'Select a room type',
    specialRequests: 'Special Requests',
    specialRequestsPlaceholder: 'Any requests or notes...',
    submit: 'Send Enquiry',
    submitting: 'Sending...',
    responseTime: "We'll get back to you within 24 hours",
    validationError: 'Please fill in your name, phone number and check-in date',
    genericError: 'Something went wrong, please try again',
    roomTypeStandard: 'Standard Room',
    roomTypeSeaView: 'Sea View Room',
    roomTypeSuite: 'Luxury Suite',
    roomTypeChalet: 'Private Chalet',
    subjectLine: 'Booking Enquiry',
  },
  confirmation: {
    title: 'Your request was sent successfully!',
    body: "We'll be in touch shortly to confirm the details",
    backHome: 'Back to Home',
  },
  pageTitles: {
    order: 'Order Now',
    beachCheckin: 'Beach Check-in',
    survey: 'Satisfaction Survey',
  },
  seo: {
    home: 'El Kheima Beach Resort — a private beachfront resort in Sharm El Maya Bay, Sharm El Sheikh. 13,000 sqm private sandy beach, authentic Italian dining, water sports, and sea-view rooms.',
    dining: "Explore El Kheima Beach Resort's dining menu — authentic Italian cuisine, a seafront cafe, and a drinks & cocktails bar.",
    booking: "Book your stay at El Kheima Beach Resort — sea-view rooms and suites in Sharm El Sheikh. We'll get back to you within 24 hours to confirm your booking.",
    confirmation: 'Your booking request at El Kheima Beach Resort has been received — our team will contact you shortly to confirm the details.',
    order: 'Order food and drinks straight from your table at El Kheima Beach Resort.',
    beachCheckin: 'Beach reservation check-in at El Kheima Beach Resort.',
    survey: 'Share your feedback about your stay at El Kheima Beach Resort — your satisfaction matters to us.',
    about: 'Discover the story of El Kheima Beach Resort and what makes us different — a private beach, authentic Italian dining, and water sports in Sharm El Sheikh.',
    contact: 'Get in touch with El Kheima Beach Resort — phone numbers, address, and a direct contact form.',
    faq: 'Answers to the most common questions about staying at El Kheima Beach Resort.',
    privacy: "El Kheima Beach Resort's privacy policy.",
    terms: "El Kheima Beach Resort's terms and conditions.",
  },
  pages: {
    about: { subtitle: 'Our story and what makes us different' },
    contact: {
      title: 'Contact Us',
      subtitle: "We'd love to hear from you — send us a message and our team will get back to you within 24 hours",
      formTitle: 'Send a Message',
      fullName: 'Full Name', fullNamePlaceholder: 'John Smith',
      email: 'Email', phone: 'Phone Number',
      subject: 'Subject', subjectPlaceholder: 'General inquiry',
      message: 'Message', messagePlaceholder: 'Write your message here...',
      submit: 'Send', submitting: 'Sending...',
      validationError: 'Please fill in your name, email, and message',
      genericError: 'Something went wrong — please try again or contact us by phone',
      successTitle: 'Your message was sent successfully!', successBody: 'Our team will get back to you shortly',
      infoTitle: 'Contact Information',
    },
    faq: {
      title: 'Frequently Asked Questions', subtitle: 'Answers to our most common questions',
      pendingNotice: 'Content is being prepared — for any question now, please contact us directly',
    },
    privacy: {
      title: 'Privacy Policy',
      pendingNotice: 'The full privacy policy will be published soon. For any question about your data, please contact us directly.',
    },
    terms: {
      title: 'Terms & Conditions',
      pendingNotice: 'The full terms & conditions will be published soon. For any question, please contact us directly.',
    },
  },
}

const ru: MarketingMessages = {
  brand: {
    name: 'El Kheima Beach Resort',
    nameNative: 'Эль-Хейма Бич Резорт',
    tagline: 'Ваше личное убежище ждёт вас',
  },
  nav: { home: 'Главная', rooms: 'Номера', dining: 'Питание', book: 'Забронировать', contact: 'Контакты', callUs: 'Позвонить', menuToggle: 'Открыть/закрыть меню', about: 'О нас', faq: 'Вопросы и ответы' },
  hero: {
    eyebrow: 'Бухта Шарм-эль-Майя • Шарм-эль-Шейх',
    title: 'El Kheima Beach Resort',
    subtitle: 'Роскошный курорт на берегу Красного моря — там, где рождаются воспоминания',
    cta: 'Забронировать',
    secondaryCta: 'Запрос на бронирование',
  },
  about: {
    title: 'Добро пожаловать в El Kheima Beach Resort',
    body: 'Расположенный в живописной бухте Шарм-эль-Майя, курорт El Kheima предлагает незабываемый отдых на территории 35 000 м² первозданного побережья, с частным песчаным пляжем и кристально чистым видом на море. Признанный лучшим пляжным курортом в регионе, мы гордимся исключительным сервисом, безупречными удобствами и созданием воспоминаний на всю жизнь.',
  },
  stats: {
    beachArea: '13 000 м²', beachAreaLabel: 'Частный песчаный пляж',
    beachLength: '225 м', beachLengthLabel: 'Кристально чистый вид на море',
    totalArea: '35 000 м²', totalAreaLabel: 'Общая площадь курорта',
    ranking: '№1', rankingLabel: 'Пляжный курорт в регионе',
  },
  valueProps: {
    title: 'Наши преимущества',
    subtitle: 'Всё для незабываемого отдыха в Шарм-эль-Шейхе',
    beach: { title: 'Частный пляж', desc: '13 000 м² частного песчаного пляжа с видом на море на 225 метров, шезлонги, зонтики и служба спасателей' },
    dining: { title: 'Настоящая итальянская кухня', desc: 'Изысканный итальянский ресторан и кафе на берегу моря, бар с коктейлями и VIP-лаунж для кальяна' },
    water: { title: 'Водные виды спорта', desc: 'Снорклинг, парасейлинг, плавание и курсы дайвинга — активности для всей семьи' },
    rooms: { title: 'Номера с видом на море', desc: 'Номера и люксы с видом на море, созданные для вашего комфорта, со всеми современными удобствами' },
    events: { title: 'Мероприятия и свадьбы', desc: 'Специальная площадка для свадеб, торжеств и особых мероприятий с потрясающим видом на море' },
    families: { title: 'Идеально для пар и семей', desc: 'Безопасные и увлекательные активности для семей и спокойная романтическая атмосфера для пар круглый год' },
  },
  rooms: {
    title: 'Наши номера и люксы',
    subtitle: 'Выберите номер, подходящий для вашего пребывания',
    loading: 'Загрузка доступных номеров...',
    empty: 'Сейчас нет свободных номеров — пожалуйста, свяжитесь с нами напрямую',
    error: 'Не удалось загрузить номера, попробуйте позже',
    perNight: 'за ночь',
    maxGuests: 'До {n} гостей',
    from: 'От',
    bookThis: 'Забронировать этот номер',
  },
  dining: {
    title: 'Меню еды и напитков',
    subtitle: 'Попробуйте наши лучшие блюда и фирменные напитки',
    outletSubtitle: 'Ознакомьтесь с полным меню',
    loading: 'Загрузка меню...',
    error: 'Не удалось загрузить меню, попробуйте позже',
    empty: 'Меню временно недоступно',
  },
  cta: {
    title: 'Начните свой отдых с нами уже сегодня',
    subtitle: 'Конкурентные цены и безупречный сервис',
    button: 'Запрос на бронирование',
  },
  contact: {
    title: 'Свяжитесь с нами',
    phone: 'Бронирование и запросы',
    address: 'Улица Мохамед Эль-Ямани, бухта Шарм-эль-Майя, Старый рынок (рядом с клубом водных видов спорта), Шарм-эль-Шейх, Южный Синай 46628',
    hours: 'Часы работы',
    hoursValue: 'Стойка регистрации 24/7 • Пляж 8:00 – закат • Ресторан 12:00 – 23:00',
    follow: 'Мы в соцсетях',
  },
  footer: {
    rights: 'Все права защищены',
    privacyLink: 'Политика конфиденциальности',
    termsLink: 'Условия использования',
  },
  booking: {
    back: 'Главная',
    title: 'Запрос на бронирование',
    subtitle: 'Мы свяжемся с вами в течение 24 часов',
    fullName: 'Полное имя',
    fullNamePlaceholder: 'Иван Иванов',
    phone: 'Номер телефона',
    email: 'Электронная почта',
    checkIn: 'Дата заезда',
    checkOut: 'Дата выезда',
    adults: 'Взрослые',
    children: 'Дети',
    roomType: 'Тип номера',
    roomTypePlaceholder: 'Выберите тип номера',
    specialRequests: 'Особые пожелания',
    specialRequestsPlaceholder: 'Любые пожелания или примечания...',
    submit: 'Отправить запрос',
    submitting: 'Отправка...',
    responseTime: 'Мы свяжемся с вами в течение 24 часов',
    validationError: 'Пожалуйста, укажите имя, телефон и дату заезда',
    genericError: 'Произошла ошибка, попробуйте ещё раз',
    roomTypeStandard: 'Стандартный номер',
    roomTypeSeaView: 'Номер с видом на море',
    roomTypeSuite: 'Люкс',
    roomTypeChalet: 'Отдельное шале',
    subjectLine: 'Запрос на бронирование',
  },
  confirmation: {
    title: 'Ваш запрос успешно отправлен!',
    body: 'Мы скоро свяжемся с вами для подтверждения деталей',
    backHome: 'Вернуться на главную',
  },
  pageTitles: {
    order: 'Заказать',
    beachCheckin: 'Регистрация на пляже',
    survey: 'Опрос удовлетворённости',
  },
  seo: {
    home: 'El Kheima Beach Resort — частный пляжный курорт в заливе Шарм-эль-Майя, Шарм-эль-Шейх. Частный песчаный пляж 13 000 м², аутентичная итальянская кухня, водные виды спорта и номера с видом на море.',
    dining: 'Меню ресторана и бара El Kheima Beach Resort — аутентичная итальянская кухня, кафе на берегу моря и бар напитков и коктейлей.',
    booking: 'Забронируйте проживание в El Kheima Beach Resort — номера и люксы с видом на море в Шарм-эль-Шейхе. Мы свяжемся с вами в течение 24 часов для подтверждения.',
    confirmation: 'Ваш запрос на бронирование в El Kheima Beach Resort получен — наша команда свяжется с вами в ближайшее время для подтверждения деталей.',
    order: 'Заказывайте еду и напитки прямо со своего столика в El Kheima Beach Resort.',
    beachCheckin: 'Регистрация пляжного бронирования в El Kheima Beach Resort.',
    survey: 'Поделитесь своим мнением о пребывании в El Kheima Beach Resort — ваше мнение важно для нас.',
    about: 'Узнайте историю El Kheima Beach Resort и что делает нас особенными — частный пляж, аутентичная итальянская кухня и водные виды спорта в Шарм-эль-Шейхе.',
    contact: 'Свяжитесь с El Kheima Beach Resort — номера телефонов, адрес и форма обратной связи.',
    faq: 'Ответы на самые распространённые вопросы о проживании в El Kheima Beach Resort.',
    privacy: 'Политика конфиденциальности El Kheima Beach Resort.',
    terms: 'Условия использования El Kheima Beach Resort.',
  },
  pages: {
    about: { subtitle: 'Наша история и что делает нас особенными' },
    contact: {
      title: 'Свяжитесь с нами',
      subtitle: 'Будем рады услышать вас — отправьте сообщение, и наша команда свяжется с вами в течение 24 часов',
      formTitle: 'Отправить сообщение',
      fullName: 'Полное имя', fullNamePlaceholder: 'Иван Иванов',
      email: 'Электронная почта', phone: 'Номер телефона',
      subject: 'Тема', subjectPlaceholder: 'Общий вопрос',
      message: 'Сообщение', messagePlaceholder: 'Напишите ваше сообщение здесь...',
      submit: 'Отправить', submitting: 'Отправка...',
      validationError: 'Пожалуйста, заполните имя, email и сообщение',
      genericError: 'Произошла ошибка — попробуйте снова или свяжитесь с нами по телефону',
      successTitle: 'Ваше сообщение успешно отправлено!', successBody: 'Наша команда свяжется с вами в ближайшее время',
      infoTitle: 'Контактная информация',
    },
    faq: {
      title: 'Часто задаваемые вопросы', subtitle: 'Ответы на самые популярные вопросы',
      pendingNotice: 'Раздел находится в разработке — по любым вопросам свяжитесь с нами напрямую',
    },
    privacy: {
      title: 'Политика конфиденциальности',
      pendingNotice: 'Полная политика конфиденциальности будет опубликована в ближайшее время. По вопросам о ваших данных свяжитесь с нами напрямую.',
    },
    terms: {
      title: 'Условия использования',
      pendingNotice: 'Полные условия использования будут опубликованы в ближайшее время. По любым вопросам свяжитесь с нами напрямую.',
    },
  },
}

const it: MarketingMessages = {
  brand: {
    name: 'El Kheima Beach Resort',
    nameNative: 'El Kheima Beach Resort',
    tagline: 'Il tuo rifugio privato ti aspetta',
  },
  nav: { home: 'Home', rooms: 'Camere', dining: 'Ristorazione', book: 'Prenota Ora', contact: 'Contatti', callUs: 'Chiamaci', menuToggle: 'Attiva/disattiva menu', about: 'Chi siamo', faq: 'FAQ' },
  hero: {
    eyebrow: 'Baia di Sharm El Maya • Sharm El Sheikh',
    title: 'El Kheima Beach Resort',
    subtitle: 'Un resort di lusso sulla spiaggia del Mar Rosso — dove nascono i ricordi',
    cta: 'Prenota Ora',
    secondaryCta: 'Richiedi Informazioni',
  },
  about: {
    title: 'Benvenuti all’El Kheima Beach Resort',
    body: 'Situato nella splendida baia di Sharm El Maya, El Kheima Beach Resort offre una fuga indimenticabile su 35.000 m² di incontaminata proprietà fronte mare, con una spiaggia privata di sabbia e acque cristalline. Classificato come il miglior resort sulla spiaggia della zona, siamo orgogliosi del nostro servizio eccezionale, delle strutture impeccabili e della creazione di ricordi che durano una vita.',
  },
  stats: {
    beachArea: '13.000 m²', beachAreaLabel: 'Spiaggia privata di sabbia',
    beachLength: '225 m', beachLengthLabel: 'Vista mare cristallina',
    totalArea: '35.000 m²', totalAreaLabel: 'Area totale del resort',
    ranking: '#1', rankingLabel: 'Resort sulla spiaggia della zona',
  },
  valueProps: {
    title: 'I Nostri Punti di Forza',
    subtitle: 'Tutto ciò di cui hai bisogno per una vacanza indimenticabile a Sharm El Sheikh',
    beach: { title: 'Spiaggia Privata', desc: '13.000 m² di spiaggia privata di sabbia con 225 metri di vista mare cristallina, lettini, ombrelloni e servizio di salvataggio' },
    dining: { title: 'Autentica Cucina Italiana', desc: 'Un raffinato ristorante italiano e un caffè sul mare, un bar per cocktail e bevande, e una lounge VIP per lo shisha' },
    water: { title: 'Sport Acquatici', desc: 'Snorkeling, parasailing, nuoto e corsi di immersione — attività acquatiche complete per tutta la famiglia' },
    rooms: { title: 'Camere Vista Mare', desc: 'Camere e suite fronte mare progettate per il tuo comfort, con tutti i comfort moderni' },
    events: { title: 'Eventi e Matrimoni', desc: 'Una location dedicata a matrimoni, celebrazioni ed eventi speciali con una splendida vista sul mare' },
    families: { title: 'Ideale per Coppie e Famiglie', desc: 'Attività sicure e divertenti per le famiglie e un’atmosfera romantica e tranquilla per le coppie, tutto l’anno' },
  },
  rooms: {
    title: 'Le Nostre Camere e Suite',
    subtitle: 'Scegli la camera più adatta al tuo soggiorno',
    loading: 'Caricamento delle camere disponibili...',
    empty: 'Nessuna camera disponibile al momento — vi preghiamo di contattarci direttamente',
    error: 'Impossibile caricare le camere al momento, riprova più tardi',
    perNight: 'a notte',
    maxGuests: 'Fino a {n} ospiti',
    from: 'A partire da',
    bookThis: 'Prenota Questa Camera',
  },
  dining: {
    title: 'Menu Cibo e Bevande',
    subtitle: 'Assapora i nostri piatti migliori e le bevande esclusive',
    outletSubtitle: 'Scopri il nostro menu completo',
    loading: 'Caricamento del menu...',
    error: 'Impossibile caricare il menu al momento, riprova più tardi',
    empty: 'Il menu non è al momento disponibile',
  },
  cta: {
    title: 'Inizia Oggi la Tua Esperienza Con Noi',
    subtitle: 'Tariffe competitive e un servizio impareggiabile',
    button: 'Richiedi Informazioni',
  },
  contact: {
    title: 'Contattaci',
    phone: 'Prenotazioni e Informazioni',
    address: 'Mohamed El Yamany Street, Baia di Sharm El Maya, Old Market (accanto al Water Sports Club), Sharm El Sheikh, Sinai del Sud 46628',
    hours: 'Orari di Apertura',
    hoursValue: 'Reception 24/7 • Spiaggia 8:00 – tramonto • Ristorante 12:00 – 23:00',
    follow: 'Seguici',
  },
  footer: {
    rights: 'Tutti i diritti riservati',
    privacyLink: 'Informativa sulla privacy',
    termsLink: 'Termini e condizioni',
  },
  booking: {
    back: 'Home',
    title: 'Richiesta di Prenotazione',
    subtitle: 'Ti risponderemo entro 24 ore',
    fullName: 'Nome Completo',
    fullNamePlaceholder: 'Mario Rossi',
    phone: 'Numero di Telefono',
    email: 'Email',
    checkIn: 'Data di Arrivo',
    checkOut: 'Data di Partenza',
    adults: 'Adulti',
    children: 'Bambini',
    roomType: 'Tipo di Camera',
    roomTypePlaceholder: 'Seleziona un tipo di camera',
    specialRequests: 'Richieste Speciali',
    specialRequestsPlaceholder: 'Eventuali richieste o note...',
    submit: 'Invia Richiesta',
    submitting: 'Invio in corso...',
    responseTime: 'Ti risponderemo entro 24 ore',
    validationError: 'Inserisci nome, numero di telefono e data di arrivo',
    genericError: 'Si è verificato un errore, riprova',
    roomTypeStandard: 'Camera Standard',
    roomTypeSeaView: 'Camera Vista Mare',
    roomTypeSuite: 'Suite di Lusso',
    roomTypeChalet: 'Chalet Privato',
    subjectLine: 'Richiesta di Prenotazione',
  },
  confirmation: {
    title: 'La tua richiesta è stata inviata con successo!',
    body: 'Ti contatteremo a breve per confermare i dettagli',
    backHome: 'Torna alla Home',
  },
  pageTitles: {
    order: 'Ordina ora',
    beachCheckin: 'Check-in spiaggia',
    survey: 'Sondaggio di soddisfazione',
  },
  seo: {
    home: 'El Kheima Beach Resort — un resort privato sulla spiaggia nella baia di Sharm El Maya, Sharm El Sheikh. Spiaggia privata di 13.000 mq, autentica cucina italiana, sport acquatici e camere vista mare.',
    dining: 'Scopri il menu di El Kheima Beach Resort — autentica cucina italiana, un caffè fronte mare e un bar per drink e cocktail.',
    booking: 'Prenota il tuo soggiorno a El Kheima Beach Resort — camere e suite vista mare a Sharm El Sheikh. Ti contatteremo entro 24 ore per confermare la prenotazione.',
    confirmation: 'La tua richiesta di prenotazione presso El Kheima Beach Resort è stata ricevuta — il nostro team ti contatterà a breve per confermare i dettagli.',
    order: 'Ordina cibo e bevande direttamente dal tuo tavolo a El Kheima Beach Resort.',
    beachCheckin: 'Check-in della prenotazione spiaggia a El Kheima Beach Resort.',
    survey: 'Condividi la tua opinione sul soggiorno a El Kheima Beach Resort — la tua soddisfazione è importante per noi.',
    about: 'Scopri la storia di El Kheima Beach Resort e cosa ci rende unici — spiaggia privata, autentica cucina italiana e sport acquatici a Sharm El Sheikh.',
    contact: 'Contatta El Kheima Beach Resort — numeri di telefono, indirizzo e un modulo di contatto diretto.',
    faq: 'Risposte alle domande più comuni sul soggiorno a El Kheima Beach Resort.',
    privacy: 'Informativa sulla privacy di El Kheima Beach Resort.',
    terms: 'Termini e condizioni di El Kheima Beach Resort.',
  },
  pages: {
    about: { subtitle: 'La nostra storia e cosa ci rende unici' },
    contact: {
      title: 'Contattaci',
      subtitle: 'Saremo felici di sentirti — inviaci un messaggio e il nostro team ti risponderà entro 24 ore',
      formTitle: 'Invia un messaggio',
      fullName: 'Nome completo', fullNamePlaceholder: 'Mario Rossi',
      email: 'Email', phone: 'Numero di telefono',
      subject: 'Oggetto', subjectPlaceholder: 'Richiesta generale',
      message: 'Messaggio', messagePlaceholder: 'Scrivi qui il tuo messaggio...',
      submit: 'Invia', submitting: 'Invio in corso...',
      validationError: 'Compila nome, email e messaggio',
      genericError: 'Si è verificato un errore — riprova o contattaci telefonicamente',
      successTitle: 'Il tuo messaggio è stato inviato con successo!', successBody: 'Il nostro team ti risponderà a breve',
      infoTitle: 'Informazioni di contatto',
    },
    faq: {
      title: 'Domande frequenti', subtitle: 'Risposte alle domande più comuni',
      pendingNotice: 'Contenuto in preparazione — per qualsiasi domanda, contattaci direttamente',
    },
    privacy: {
      title: 'Informativa sulla privacy',
      pendingNotice: "L'informativa completa sulla privacy sarà pubblicata a breve. Per domande sui tuoi dati, contattaci direttamente.",
    },
    terms: {
      title: 'Termini e condizioni',
      pendingNotice: 'I termini e condizioni completi saranno pubblicati a breve. Per qualsiasi domanda, contattaci direttamente.',
    },
  },
}

export const marketingMessages: Record<'ar' | 'en' | 'ru' | 'it', { marketing: MarketingMessages }> = {
  ar: { marketing: ar },
  en: { marketing: en },
  ru: { marketing: ru },
  it: { marketing: it },
}

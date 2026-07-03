/**
 * Real brand/contact constants for El Kheima Beach Resort, sourced from
 * /home/wego/projects/elkheima-beach-resort-marketing/01_brand/contact_info.csv
 * and CONTACT_INFO_UPDATED.md (updated 2026-03-09). Kept in one place so the
 * header/footer/booking views don't repeat magic strings.
 */

export const RESORT = {
  phones: ['01004444300', '01228879935'],
  whatsapp: '01004444300',
  email: 'info@alkhaymaresort.com',
  mapUrl: 'https://maps.google.com/?cid=11407870575090749929',
  website: 'https://alkhaymaresort.com',
  social: {
    facebook: 'https://facebook.com/alkhaymaresort',
    instagram: 'https://instagram.com/alkhaymaresort',
  },
} as const

/**
 * The one real branch seeded in the dev DB (`WegoSharm Resort`, code
 * WSR-001 — see backend/app/seed.py::_seed_branch). The public room-types
 * endpoint requires a branch_id query param; there is currently only ever
 * one branch in this system (single-property resort, see CLAUDE.md §4), so
 * this is hardcoded rather than made configurable.
 */
export const PUBLIC_BRANCH_ID = 1

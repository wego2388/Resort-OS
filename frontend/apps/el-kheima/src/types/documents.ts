export type DocumentScope = 'branch' | 'employee'
export type DocumentVisibility =
  | 'management'
  | 'owner_visible'
  | 'hr_confidential'
  | 'employee_visible'

export interface VaultDocument {
  id: string
  scope: DocumentScope
  employee_id: number | null
  doc_type: string
  visibility: DocumentVisibility
  title: string
  description: string | null
  issue_date: string | null
  expiry_date: string | null
  original_filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  version_number: number
  uploaded_by: number | null
  created_at: string
  updated_at: string
  days_until_expiry: number | null
  is_deleted: boolean
  is_superseded: boolean
}

export interface DocumentListResponse {
  items: VaultDocument[]
  total: number
  page: number
  size: number
}

export interface ExpiringDocument {
  id: string
  scope: DocumentScope
  employee_id: number | null
  employee_name: string | null
  doc_type: string
  title: string
  expiry_date: string
  days_remaining: number
}

export const BRANCH_DOCUMENT_TYPES = [
  'commercial_register',
  'tourism_license',
  'fire_permit',
  'health_certificate',
  'building_permit',
  'liquor_license',
  'insurance_property',
  'supplier_contract',
  'lease_agreement',
  'bank_account_docs',
  'other_branch',
] as const

export const EMPLOYEE_DOCUMENT_TYPES = [
  'employment_contract',
  'national_id_copy',
  'passport_copy',
  'social_insurance_form',
  'medical_clearance',
  'experience_cert',
  'academic_cert',
  'resignation_letter',
  'warning_letter',
  'other_employee',
] as const

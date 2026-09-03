/**
 * Type definitions for TenantModal component
 * All types are strictly typed with no 'any' usage
 */

import { Tenant, TenantStatus, TenantType } from '../../types/tenant';

/**
 * Status transformation mapping from various input formats to standard TenantStatus
 */
export const STATUS_MAPPING: Record<string, TenantStatus> = {
  'active': TenantStatus.ACTIVE,
  'inactive': TenantStatus.INACTIVE,
  'pending': TenantStatus.PENDING,
  'evicted': TenantStatus.EVICTED,
  'moved out': TenantStatus.MOVED_OUT,
  'moved_out': TenantStatus.MOVED_OUT,
} as const;

/**
 * Form data interface for tenant creation/editing
 * Matches the structure used in the form state
 */
export interface TenantFormData {
  tenant_type: TenantType;
  first_name: string;
  last_name: string;
  company_name: string;
  contact_person: string;
  phone: string;
  email: string;
  status: TenantStatus;
}

/**
 * Field error map - tracks validation errors for each form field
 */
export type FieldErrors = Partial<Record<keyof TenantFormData, string>>;

/**
 * Touched field map - tracks which fields have been interacted with
 */
export type TouchedFields = Partial<Record<keyof TenantFormData, boolean>>;

/**
 * Props for the TenantModal component
 */
export interface TenantModalProps {
  /** Whether the modal is currently open */
  isOpen: boolean;
  
  /** Callback to close the modal */
  onClose: () => void;
  
  /** Callback when tenant is successfully saved - receives the created tenant */
  onSave: (tenant: TenantResponse) => void;
  
  /** Source identifier for where the modal was opened from (affects closing behavior) */
  source: string;
  
  /** Existing tenant data for editing (optional) */
  tenant?: Partial<Tenant>;
  
  /** Property ID to associate with the tenant (optional) */
  propertyId?: number | null;
  
  /** Unit ID to associate with the tenant (optional) */
  unitId?: number | null;
  
  /** Unit name for display purposes (optional) */
  unitName?: string;
}

/**
 * Tenant response from API with additional context data
 */
export interface TenantResponse extends Tenant {
  /** Unit name for display */
  unit?: string;
  
  /** Unit ID association (overrides parent to allow explicit null) */
  unit_id?: number | null;
}

/**
 * Validation error from API (Pydantic validation error format)
 */
export interface ValidationErrorDetail {
  /** Location of the error (e.g., ['body', 'email']) */
  loc: (string | number)[];
  
  /** Error message */
  msg: string;
  
  /** Error type (e.g., 'value_error.email') */
  type: string;
}

/**
 * API error response structure
 */
export interface ApiErrorResponse {
  /** HTTP status code */
  status?: number;
  
  /** Error data from response */
  data?: {
    /** Detailed error message or validation errors */
    detail?: string | ValidationErrorDetail[];
  };
  
  /** Error message */
  message?: string;
}

/**
 * Type guard to check if error detail is an array of validation errors
 */
export function isValidationErrorArray(
  detail: string | ValidationErrorDetail[] | undefined
): detail is ValidationErrorDetail[] {
  return Array.isArray(detail);
}

/**
 * Type guard to check if an error is an API error response
 */
export function isApiErrorResponse(error: unknown): error is ApiErrorResponse {
  return (
    typeof error === 'object' &&
    error !== null &&
    ('status' in error || 'data' in error || 'message' in error)
  );
}

/**
 * Field names that can be validated
 */
export type ValidatableFieldName = keyof TenantFormData;

/**
 * Form change event type
 */
export type FormChangeEvent = React.ChangeEvent<HTMLInputElement>;

/**
 * Form submit event type
 */
export type FormSubmitEvent = React.FormEvent<HTMLFormElement>;

/**
 * Input blur event type
 */
export type InputBlurEvent = React.FocusEvent<HTMLInputElement>;

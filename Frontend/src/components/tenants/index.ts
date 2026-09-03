/**
 * Tenant components barrel export
 * Provides centralized exports for all tenant-related components
 */

export { default as TenantModal } from './TenantModal';
export type { TenantModalProps, TenantResponse } from './TenantModal.types';

// Export types for external use
export type {
  TenantFormData,
  FieldErrors,
  TouchedFields,
  ValidatableFieldName,
  FormChangeEvent,
  FormSubmitEvent,
  InputBlurEvent,
} from './TenantModal.types';

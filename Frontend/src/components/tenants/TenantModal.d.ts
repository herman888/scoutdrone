/**
 * Type definitions for TenantModal component
 * 
 * This file provides external type definitions for consumers of TenantModal.
 * For internal types, see TenantModal.types.ts
 */

import React from 'react';
import type { Tenant } from '../../types/tenant';
import type { TenantModalProps, TenantResponse } from './TenantModal.types';

// Re-export types for consumers
export type { TenantModalProps, TenantResponse };

/**
 * TenantModal - A fully typed modal component for creating new tenant profiles
 * 
 * @component
 * @example
 * ```tsx
 * <TenantModal
 *   isOpen={isOpen}
 *   onClose={() => setIsOpen(false)}
 *   onSave={(tenant) => console.log('Created tenant:', tenant)}
 *   source="tenants-page"
 *   propertyId={123}
 * />
 * ```
 */
declare const TenantModal: React.FC<TenantModalProps>;

export default TenantModal;

/**
 * Type definitions for the Integrations page and related components
 */

// Integration status types
export type IntegrationStatus = 'connected' | 'not_connected' | 'connecting' | 'disconnecting' | 'error';

export type SyncOperation = 'payments' | 'invoices' | 'expenses' | 'initial' | 'all';

// QuickBooks API response types
export interface QuickBooksStatus {
  connected: boolean;
  connected_at?: string;
  company_name?: string;
  last_sync?: string;
  error?: string;
}

export interface QuickBooksSyncResponse {
  success: boolean;
  message: string;
  synced_count?: number;
  failed_count?: number;
  errors?: string[];
}

export interface QuickBooksConnectResponse {
  success: boolean;
  redirect_url?: string;
  error?: string;
}

// Operation state using discriminated unions for better type safety
export type OperationState =
  | { type: 'idle' }
  | { type: 'loading'; operation?: string }
  | { type: 'syncing'; operation: SyncOperation }
  | { type: 'error'; message: string };

// Component prop interfaces
export interface ErrorMessageProps {
  error: string | null;
  onRetry: () => void;
}

export interface QuickBooksCardProps {
  status: QuickBooksStatus | null;
  operationState: OperationState;
  onConnect: () => void;
  onDisconnect: () => void;
  disabled?: boolean; // For temporarily disabling functionality
}

export interface PlaceholderCardProps {
  title?: string;
  description?: string;
  icon?: string;
  className?: string;
}

export interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'primary' | 'secondary';
  isLoading?: boolean;
}

// Custom hook return types
export interface UseQuickBooksIntegrationReturn {
  // State
  status: QuickBooksStatus | null;
  operationState: OperationState;
  showConfirmDisconnect: boolean;

  // Actions
  handleConnect: () => Promise<void>;
  handleDisconnect: () => void;
  handleConfirmDisconnect: () => Promise<void>;
  handleCancelDisconnect: () => void;
  handleSyncAll: () => Promise<void>;

  // Utilities
  refreshStatus: () => Promise<void>;
  isOperationInProgress: boolean;
}

// URL parameter types removed as they're now handled directly in useQuickBooksIntegration

// Integration card data structure for future extensibility
export interface IntegrationProvider {
  id: string;
  name: string;
  description: string;
  logoUrl: string;
  status: IntegrationStatus;
  isEnabled: boolean;
  comingSoon?: boolean;
  features?: string[];
}

// Event types for better error handling and analytics
export interface IntegrationEvent {
  type: 'connect' | 'disconnect' | 'sync' | 'error';
  provider: string;
  operation?: SyncOperation;
  timestamp: Date;
  success: boolean;
  error?: string;
  metadata?: Record<string, any>;
}

// Performance optimization types
export interface IntegrationsPageState {
  quickBooksStatus: QuickBooksStatus | null;
  operationState: OperationState;
  showConfirmDisconnect: boolean;
  lastRefresh: Date | null;
}

// API error response structure
export interface IntegrationApiError {
  message: string;
  code?: string;
  details?: Record<string, unknown>;
  operation?: SyncOperation;
}

// Account Mapping Types
// These support the tax account mapping feature that fixes "No tax details found" warning

export interface AccountMapping {
  id: number;
  mapping_type: string;
  brikli_key: string;
  quickbooks_account_id: string;
  quickbooks_account_name: string;
  quickbooks_account_type?: string;
  created_at: string;
  updated_at: string;
}

export interface AccountMappingCreate {
  mapping_type: string;
  brikli_key: string;
  quickbooks_account_id: string;
  quickbooks_account_name: string;
  quickbooks_account_type?: string;
}

export interface QuickBooksAccount {
  id: string;
  name: string;
  account_type: string;
  account_sub_type?: string;
  active: boolean;
}

export interface AutoDetectMappingResponse {
  detected: Record<string, {
    id: string;
    name: string;
    account_type: string;
    matched_pattern: string;
  }>;
  saved: AccountMapping[];
}

// Canadian Tax Types
export type CanadianTaxType = 'GST' | 'HST' | 'PST' | 'QST';

export const CANADIAN_TAX_TYPES: CanadianTaxType[] = ['GST', 'HST', 'PST', 'QST'];

export const TAX_TYPE_LABELS: Record<CanadianTaxType, string> = {
  GST: 'GST (Goods and Services Tax)',
  HST: 'HST (Harmonized Sales Tax)',
  PST: 'PST (Provincial Sales Tax)',
  QST: 'QST (Quebec Sales Tax)',
};

// QuickBooks Settings Types
// These control auto-sync behavior, entity sync scope, and notification preferences

export interface QuickBooksSettings {
  auto_sync_enabled: boolean;   // Enable webhook-triggered auto-sync
  sync_customers: boolean;      // Sync Customer entities
  sync_invoices: boolean;       // Sync Invoice entities
  sync_payments: boolean;       // Sync Payment entities
  sync_expenses: boolean;       // Sync Purchase/Expense entities
  notify_on_sync: boolean;      // Send in-app notifications on sync events
}

export interface QuickBooksConnectionHealth {
  last_sync_at: string | null;
  error_count: number;
  last_error: string | null;
}

export interface QuickBooksSettingsResponse {
  settings: QuickBooksSettings;
  connection_health: QuickBooksConnectionHealth;
}

export interface QuickBooksSettingsUpdate {
  auto_sync_enabled?: boolean;
  sync_customers?: boolean;
  sync_invoices?: boolean;
  sync_payments?: boolean;
  sync_expenses?: boolean;
  notify_on_sync?: boolean;
}

// Default settings for new users or when settings haven't been configured
export const DEFAULT_QUICKBOOKS_SETTINGS: QuickBooksSettings = {
  auto_sync_enabled: true,
  sync_customers: true,
  sync_invoices: true,
  sync_payments: true,
  sync_expenses: true,
  notify_on_sync: true,
};
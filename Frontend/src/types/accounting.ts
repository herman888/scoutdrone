// Comprehensive type definitions for accounting domain

export interface TaxDetail {
  id?: number;
  tax_name: string;
  tax_rate: string; // Backend uses Decimal which serializes to string
  tax_amount?: string; // Backend uses Decimal which serializes to string
}

export interface InvoiceLineItem {
  id?: number;
  invoice_id?: number;
  description: string;
  quantity: string; // Backend uses Decimal which serializes to string
  unit_price: string; // Backend uses Decimal which serializes to string
  line_total: string; // Backend uses Decimal which serializes to string (auto-calculated)
  is_taxable: boolean;
  expense_category?: string;
  sort_order: number;
  created_at?: string;
  updated_at?: string;
}

export type RecipientType = 'tenant' | 'ownership_entity' | 'vendor';

export interface RecipientSnapshot {
  name: string;
  company?: string;
  email?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  province?: string;
  postal_code?: string;
  country?: string;
  tax_number?: string;
}

export interface Expense {
  id: number;
  property_id: number;
  property_name?: string;
  category: string;
  subtotal_amount: string; // Backend uses Decimal which serializes to string
  total_amount: string; // Backend uses Decimal which serializes to string
  tax_amount?: string; // Backend uses Decimal which serializes to string
  expense_date: string;
  payment_method?: string;
  receipt_url?: string | null;
  quickbooks_id?: string | null;
  description?: string;
  source?: string;
  has_receipt?: boolean;
  taxes?: TaxDetail[];
  created_at?: string;
  updated_at?: string;
}

export interface CreateExpenseRequest {
  property_id: number;
  category: string;
  subtotal_amount: string; // Backend uses Decimal which serializes to string
  expense_date: string;
  description?: string;
  receipt_url?: string | null;
  payment_method?: string;
  taxes?: Array<{
    tax_name: string;
    tax_rate: string; // Backend uses Decimal which serializes to string
  }>;
}

export interface UpdateExpenseRequest extends Partial<CreateExpenseRequest> {
  id: number;
}

export interface Invoice {
  id: number;
  invoice_number: string;
  amount: string; // Backend uses Decimal which serializes to string (grand total)
  description?: string;
  issue_date: string;
  due_date: string;
  status: string;
  
  // Delivery method
  delivery_method?: 'save_locally' | 'send_invoice' | 'request_payment';
  
  // Accounting context
  property_id?: number;
  unit_id?: number;
  
  // Recipient information
  recipient_type?: RecipientType;
  tenant_id?: number;
  ownership_entity_id?: string; // UUID
  vendor_id?: number;
  
  // Recipient snapshot (immutable)
  recipient_name?: string;
  recipient_company?: string;
  recipient_email?: string;
  recipient_address_line1?: string;
  recipient_address_line2?: string;
  recipient_city?: string;
  recipient_province?: string;
  recipient_postal_code?: string;
  recipient_country?: string;
  recipient_tax_number?: string;
  
  // Line items (NEW)
  line_items?: InvoiceLineItem[];
  
  // Taxes
  taxes?: TaxDetail[];
  
  // Audit and workflow
  created_by_user_id?: string; // UUID
  is_draft?: boolean;
  issued_at?: string;
  issued_by_user_id?: string; // UUID
  
  // PDF Storage
  pdf_blob_url?: string | null;
  pdf_generated_at?: string | null;
  
  // Stripe Integration
  stripe_invoice_id?: string | null;
  hosted_invoice_url?: string | null;
  stripe_invoice_pdf?: string | null;
  
  // Metadata
  quickbooks_id?: string | null;
  created_at?: string;
  updated_at?: string;
  
  // Related entities
  property?: {
    id: number;
    name: string;
  };
  tenant?: {
    id: number;
    full_name?: string;
    first_name?: string;
    last_name?: string;
    company_name?: string;
    tenant_type?: string;
  };
  ownership_entity?: {
    id: string;
    name: string;
  };
  vendor?: {
    id: number;
    company_name: string;
  };
  created_by?: {
    id: string;
    email: string;
    full_name?: string;
  };
  issued_by?: {
    id: string;
    email: string;
    full_name?: string;
  };
}

export interface CreateInvoiceRequest {
  invoice_number: string;
  amount: string; // Backend uses Decimal which serializes to string (legacy/fallback)
  description: string;
  issue_date: string;
  due_date: string;
  status?: string;
  
  // Delivery method
  delivery_method?: 'save_locally' | 'send_invoice' | 'request_payment';
  
  // Draft flag
  is_draft?: boolean;
  
  // Accounting context
  property_id?: number;
  unit_id?: number;
  
  // Recipient information
  recipient_type?: RecipientType;
  tenant_id?: number;
  ownership_entity_id?: string; // UUID
  vendor_id?: number;
  
  // Line items (NEW - preferred)
  line_items?: Array<{
    description: string;
    quantity: string; // Decimal
    unit_price: string; // Decimal
    line_total?: string; // Decimal (auto-calculated)
    is_taxable: boolean;
    expense_category?: string;
    sort_order?: number;
  }>;
  
  // Taxes
  taxes?: Array<{
    tax_name: string;
    tax_rate: string; // Backend uses Decimal which serializes to string
  }>;
}

export interface UpdateInvoiceRequest extends Partial<CreateInvoiceRequest> {
  id: number;
}

export interface Payment {
  id: number;
  invoice_id?: number;
  tenant_id?: number;
  amount: string; // Backend uses Decimal which serializes to string
  payment_date: string;
  payment_method: string;
  description?: string;
  quickbooks_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CreatePaymentRequest {
  lease_id?: number | null;
  tenant_id?: number | null;
  property_id?: number | null;
  invoice_id?: number;
  tenant_name?: string | null;
  amount: string | number; // Backend uses Decimal which serializes to string
  payment_date?: string | null;
  payment_method?: string;
  status?: string;
  description?: string;
  receipt_url?: string | null;
  transaction_reference?: string | null;
  reduction_amount?: number | null;
  reduction_reason?: string | null;
}

export interface UpdatePaymentRequest extends Partial<CreatePaymentRequest> {
  id: number;
}

// Pagination types
export interface PaginatedResponse<T> {
  items: T[];
  total?: number;
  has_more?: boolean;
  page?: number;
  limit?: number;
}

export type ExpensesResponse = PaginatedResponse<Expense>;
export type InvoicesResponse = PaginatedResponse<Invoice>;
export type PaymentsResponse = PaginatedResponse<Payment>;

// Query parameter types
export interface BaseQueryParams {
  limit?: number;
  offset?: number;
  search?: string;
  start_date?: string;
  end_date?: string;
}

export interface ExpenseQueryParams extends BaseQueryParams {
  category?: string;
  property_id?: number;
}

export interface InvoiceQueryParams extends BaseQueryParams {
  status?: string;
  property_id?: number;
  tenant_id?: number;
}

export interface PaymentQueryParams extends BaseQueryParams {
  invoice_id?: number;
  tenant_id?: number;
}

// Tax Preferences types (for Phase 3)
export interface SmartTaxRecommendation {
  tax_name: string;
  tax_rate: string; // Backend uses Decimal which serializes to string
  confidence: number;
  source: 'property_default' | 'user_default' | 'provincial_default' | 'usage_analysis' | 'historical_usage' | 'none';
  explanation?: string;
  reasoning?: string; // For backward compatibility with existing modals
}

export interface TaxPreferenceRequest {
  tax_name: string;
  tax_rate: string; // Backend uses Decimal which serializes to string
  property_id?: number; // If provided, sets property default; otherwise user default
}

export interface TaxDetail {
  tax_name: string;
  tax_rate: string; // Backend uses Decimal which serializes to string
}

export interface UserTaxDefaults {
  default_taxes?: {
    taxes: TaxDetail[];
  } | null;
}

export interface PropertyTaxDefaults {
  default_taxes?: {
    taxes: TaxDetail[];
  } | null;
}

// Receipt parsing types
export interface ParsedReceiptData {
  category?: string;
  amount?: string; // Backend uses Decimal which serializes to string
  subtotal_amount?: string; // Backend uses Decimal which serializes to string
  tax_amount?: string; // Backend uses Decimal which serializes to string
  expense_date?: string;
  description?: string;
  merchant?: string;
  taxes?: Array<{
    tax_name: string;
    tax_rate: string; // Backend uses Decimal which serializes to string
    tax_amount?: string; // Backend uses Decimal which serializes to string
  }>;
}

export interface ReceiptParsingResponse {
  success: boolean;
  data?: ParsedReceiptData;
  error?: string;
}

// CSV Import types
export interface CSVImportResponse {
  success: boolean;
  imported_count: number;
  failed_count: number;
  errors?: string[];
}

/**
 * Form data types for modals - UI-friendly field names and types
 * 
 * IMPORTANT: Form field names differ from API field names for better UX:
 * - Form 'amount' field → API 'subtotal_amount' field  
 * - Form 'property_id' (string) → API 'property_id' (number)
 * 
 * Transformation happens in form hooks (useExpenseForm, useInvoiceForm)
 * before sending data to the API endpoints.
 */
export interface ExpenseFormData {
  id?: string; // Optional for create mode, required for edit mode
  category: string;
  amount: string; // UI field name - transformed to 'subtotal_amount' for CreateExpenseRequest API
  expense_date: string;
  description: string;
  receipt_url: string | null;
  property_id: string; // Parsed to number for API
  property_name: string;
  payment_method: string;
  taxes: Array<{
    tax_name: string;
    tax_rate: string;
  }>;
}

export interface InvoiceLineItemFormData {
  description: string;
  quantity: string;
  unit_price: string;
  line_total?: string; // Auto-calculated
  is_taxable: boolean;
  expense_category?: string;
  sort_order?: number;
}

export interface InvoiceFormData {
  id?: string; // Optional for create mode, required for edit mode
  invoice_number: string;
  amount: string; // Legacy field - auto-calculated from line items + taxes
  description: string;
  issue_date: string;
  due_date: string;
  status: string;
  
  // Accounting context
  property_id: string; // Parsed to number for API
  property_name: string;
  unit_id?: string; // Parsed to number for API
  
  // Recipient information
  recipient_type?: RecipientType;
  tenant_id: string; // Parsed to number for API
  tenant_name: string;
  ownership_entity_id?: string; // UUID
  ownership_entity_name?: string;
  vendor_id?: string; // Parsed to number for API
  vendor_name?: string;
  
  // Line items (NEW)
  line_items: InvoiceLineItemFormData[];
  
  // Taxes
  taxes: Array<{
    tax_name: string;
    tax_rate: string;
  }>;
}

// Error types
export interface ApiError {
  message: string;
  code?: string;
  details?: Record<string, unknown>;
}

// Constants
export const EXPENSE_CATEGORIES = [
  'maintenance',
  'utilities',
  'taxes',
  'insurance',
  'administrative',
  'other'
] as const;

export const PAYMENT_METHODS = [
  'Credit Card',
  'Debit Card',
  'Bank Transfer',
  'Cash',
  'Check',
  'Other'
] as const;

export const INVOICE_STATUSES = [
  'Draft',
  'Pending', 
  'Paid',
  'Partial',
  'Overdue',
  'Cancelled',
  'Refunded',
  'Void',
  'Uncollectible'
] as const;

export type ExpenseCategory = typeof EXPENSE_CATEGORIES[number];
export type PaymentMethod = typeof PAYMENT_METHODS[number];
export type InvoiceStatus = typeof INVOICE_STATUSES[number];

// ============================================================================
// Accounting Context Types
// ============================================================================

/**
 * Type definitions for the Accounting module context and state
 */

export interface MonthlyMetrics {
  revenue: number;
  expenses: number;
  netIncome: number;
}

export interface YTDMetrics {
  revenue: number;
  expenses: number;
  netIncome: number;
}

export interface SnapshotMetrics {
  occupancyRate: number;
  paidRent: number;
  totalRent: number;
  avgRent: number;
}

export interface AccountingData {
  monthly: MonthlyMetrics;
  ytd: YTDMetrics;
  snapshot: SnapshotMetrics;
}

export interface IncomeByProperty {
  id: number;
  name: string;
  monthlyIncome: number;
  occupancyRate: number;
}

export interface RevenueTrend {
  period: string;
  revenue: number | string;
  expenses: number | string;
}

export interface OverviewData {
  monthly_revenue: number | string;
  monthly_expenses: number | string;
  monthly_net_income: number | string;
  ytd_revenue: number | string;
  ytd_expenses: number | string;
  ytd_net_income: number | string;
  occupancy_rate: number | string;
  average_rent: number | string;
  revenue_trends?: RevenueTrend[];
}

export interface AccountingContextValue {
  // State
  overviewData: OverviewData | null;
  setOverviewData: React.Dispatch<React.SetStateAction<OverviewData | null>>;
  accountingData: AccountingData;
  setAccountingData: React.Dispatch<React.SetStateAction<AccountingData>>;
  incomeByPropertyData: IncomeByProperty[];
  setIncomeByPropertyData: React.Dispatch<React.SetStateAction<IncomeByProperty[]>>;
  loading: boolean;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  error: Error | null;
  setError: React.Dispatch<React.SetStateAction<Error | null>>;
  
  // Modal state
  showFilePreviewModal: boolean;
  setShowFilePreviewModal: React.Dispatch<React.SetStateAction<boolean>>;
  fileToPreviewUrl: string | null;
  setFileToPreviewUrl: React.Dispatch<React.SetStateAction<string | null>>;
  filePreviewName: string;
  setFilePreviewName: React.Dispatch<React.SetStateAction<string>>;
  
  // Constants
  currentMonth: number;
  currentYear: number;
  
  // Functions
  refreshOverviewData: () => void;
  handlePreviewReceipt: (url: string, name?: string) => void;
  closeFilePreview: () => void;
  updateAccountingMetrics: (newData: Partial<AccountingData>) => void;
}

export interface AccountingProviderProps {
  children: React.ReactNode;
}
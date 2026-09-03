// QuickBooks Integration API Functions
import { apiRequest } from './core';

export const connectToQuickBooks = async () => {
  // Backend currently exposes GET; use GET here for compatibility
  return apiRequest("/quickbooks/connect", {
    method: "GET",
    recaptchaAction: 'quickbooks_connect',
  });
};

export const getQuickBooksStatus = async () => {
  return apiRequest("/quickbooks/status");
};

export const disconnectQuickBooks = async () => {
  return apiRequest("/quickbooks/disconnect", {
    method: "POST",
  });
};

export const handleQuickBooksCallback = async (code, realmId, state) => {
  return apiRequest(`/quickbooks/callback?code=${encodeURIComponent(code)}&realmId=${encodeURIComponent(realmId)}&state=${encodeURIComponent(state)}`, {
    method: "GET",
  });
};

export const initialQuickBooksSync = async () => {
  return apiRequest("/quickbooks/initial-sync", {
    method: "POST",
  });
};

export const syncQuickBooksPayments = async () => {
  return apiRequest("/quickbooks/sync/payments", {
    method: "POST",
  });
};

export const syncQuickBooksInvoices = async () => {
  return apiRequest("/quickbooks/sync/invoices", {
    method: "POST",
  });
};

export const syncQuickBooksExpenses = async () => {
  return apiRequest("/quickbooks/sync/expenses", {
    method: "POST",
  });
};

export const syncAllQuickBooksData = async () => {
  return apiRequest("/quickbooks/sync/all", {
    method: "POST",
  });
};

export const syncQuickBooksTransactions = async () => {
  return apiRequest("/quickbooks/sync/transactions", {
    method: "POST",
  });
};

export const getQuickBooksDiagnostics = async () => {
  return apiRequest("/quickbooks/diagnostics");
};

// Preview and Account Management
export const previewQuickBooksSync = async () => {
  return apiRequest("/quickbooks/sync/preview");
};

export const applyQuickBooksSync = async (items) => {
  return apiRequest("/quickbooks/sync/apply", {
    method: "POST",
    body: JSON.stringify(items),
  });
};

export const getQuickBooksAccounts = async () => {
  return apiRequest("/quickbooks/accounts");
};

// Account Mapping API Functions
// These enable proper tax line detection during expense sync

/**
 * Get all account mappings for the user's QuickBooks integration.
 * Returns mappings between Brikli tax types (GST, HST, PST, QST) and QB account IDs.
 */
export const getAccountMappings = async () => {
  return apiRequest("/quickbooks/accounts/mappings");
};

/**
 * Save or update an account mapping.
 * @param {Object} mapping - The mapping to save
 * @param {string} mapping.mapping_type - Type of mapping (e.g., "tax_account")
 * @param {string} mapping.brikli_key - Brikli identifier (e.g., "GST", "PST")
 * @param {string} mapping.quickbooks_account_id - The QB account ID
 * @param {string} mapping.quickbooks_account_name - Human-readable account name
 * @param {string} [mapping.quickbooks_account_type] - Optional account type
 */
export const saveAccountMapping = async (mapping) => {
  return apiRequest("/quickbooks/accounts/mappings", {
    method: "POST",
    body: JSON.stringify(mapping),
  });
};

/**
 * Auto-detect Canadian tax accounts from QuickBooks Chart of Accounts.
 * Scans accounts and matches them to GST, HST, PST, QST based on naming patterns.
 * This fixes the "No tax details found" warning.
 */
export const autoDetectAccountMappings = async () => {
  return apiRequest("/quickbooks/accounts/mappings/auto-detect", {
    method: "POST",
  });
};

/**
 * Delete an account mapping by ID.
 * @param {number} mappingId - The ID of the mapping to delete
 */
export const deleteAccountMapping = async (mappingId) => {
  return apiRequest(`/quickbooks/accounts/mappings/${mappingId}`, {
    method: "DELETE",
  });
};

/**
 * Get QuickBooks accounts that are eligible for tax mapping.
 * Returns only expense-type accounts that can be used for tax tracking.
 */
export const getTaxEligibleAccounts = async () => {
  return apiRequest("/quickbooks/accounts/tax-eligible");
};

// QuickBooks Settings API Functions
// These control auto-sync behavior, entity sync scope, and notification preferences

/**
 * Get QuickBooks integration settings for the current user.
 * Returns settings and connection health information.
 * @returns {Promise<{settings: Object, connection_health: Object}>}
 */
export const getQuickBooksSettings = async () => {
  return apiRequest("/quickbooks/settings");
};

/**
 * Update QuickBooks integration settings.
 * Only updates fields that are provided (partial update).
 * @param {Object} settings - Partial settings object to update
 * @param {boolean} [settings.auto_sync_enabled] - Enable/disable webhook auto-sync
 * @param {boolean} [settings.sync_customers] - Enable/disable customer sync
 * @param {boolean} [settings.sync_invoices] - Enable/disable invoice sync
 * @param {boolean} [settings.sync_payments] - Enable/disable payment sync
 * @param {boolean} [settings.sync_expenses] - Enable/disable expense sync
 * @param {boolean} [settings.notify_on_sync] - Enable/disable sync notifications
 * @returns {Promise<{settings: Object, connection_health: Object}>}
 */
export const updateQuickBooksSettings = async (settings) => {
  return apiRequest("/quickbooks/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
};
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-toastify';
import { X, Save, Send, Star } from 'lucide-react';
import { fetchProperties } from '../utils/api/properties';
import { fetchTenants } from '../utils/api/tenants';
import { fetchOwnershipEntities } from '../utils/api/ownershipEntities';
import { listVendors } from '../utils/api/vendors';
import { createInvoice, updateInvoice, fetchInvoice } from '../utils/api/accounting';
import { useInvoiceForm } from '../hooks/accounting/useInvoiceForm';
import { useTaxRecommendations } from '../hooks/accounting/useTaxRecommendations';
import { useLocalStorageAutoSave, loadFromLocalStorage, clearLocalStorage } from '../hooks/useLocalStorageAutoSave';
import { useConnectStatus } from '../hooks/useConnectStatus';
import { useUnsavedChangesWarning } from '../hooks/useUnsavedChangesWarning';
import { getUserTaxDefault, removeUserTaxDefault } from '../utils/api/accounting';
import RecipientSelector from '../components/accounting/shared/RecipientSelector';
import LineItemsManager from '../components/accounting/shared/LineItemsManager';
import InvoicePreview from '../components/accounting/shared/InvoicePreview';
import FinancialErrorBoundary from '../components/accounting/shared/FinancialErrorBoundary';
import SavedTaxesModal from '../components/accounting/shared/SavedTaxesModal';
import Tooltip from '../components/ui/Tooltip';
import type { Property } from '../types/property';
import type { EnrichedTenant } from '../types/tenant';
import type { TaxDetail, CreateInvoiceRequest, UpdateInvoiceRequest } from '../types/accounting';

/**
 * Dedicated full-page invoice creation interface
 * 
 * Industry-standard features:
 * - Two-column layout (form + live preview)
 * - Auto-save drafts every 10 seconds
 * - Keyboard shortcuts (Ctrl+S, Ctrl+Enter)
 * - Unsaved changes warning
 * - Breadcrumb navigation
 * - Full screen real estate for complex forms
 * 
 * Follows patterns from: Stripe, QuickBooks, Xero, FreshBooks
 */
const InvoiceCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  
  // Data state
  const [properties, setProperties] = useState<Property[]>([]);
  const [tenants, setTenants] = useState<EnrichedTenant[]>([]);
  const [ownershipEntities, setOwnershipEntities] = useState<any[]>([]);
  const [vendors, setVendors] = useState<any[]>([]);
  // Use ref to track invoice ID for reliable auto-save (avoids stale closure issues)
  const currentInvoiceIdRef = useRef<number | null>(id ? parseInt(id) : null);
  // Use ref to prevent concurrent save operations
  const isSavingRef = useRef<boolean>(false);
  
  // Update ref when ID param changes (e.g., when restoring draft)
  useEffect(() => {
    if (id) {
      const invoiceId = parseInt(id);
      if (!isNaN(invoiceId)) {
        currentInvoiceIdRef.current = invoiceId;
      }
    }
  }, [id]);

  // Delivery method selection (must be declared before useInvoiceForm)
  const [deliveryMethod, setDeliveryMethod] = useState<'save_locally' | 'send_invoice' | 'request_payment'>('save_locally');

  // Form management hook
  const {
    formData,
    lineItems,
    recipientType,
    errors,
    isSubmitting,
    calculatedTotals,
    userFavoriteTaxes,
    updateField,
    addTaxLine,
    removeTaxLine,
    updateTaxLine,
    addLineItem,
    removeLineItem,
    updateLineItem,
    setRecipientType,
    submitForm,
    setUserFavoriteTaxes,
  } = useInvoiceForm({
    mode: id ? 'edit' : 'create',
    invoiceId: id ? parseInt(id) : undefined,
    deliveryMethod: deliveryMethod,
    onSuccess: async (response) => {
      console.log('📋 Invoice created and finalized:', response?.id, 'Delivery method:', deliveryMethod);
      
      // Store invoice ID from response
      if (response?.id) {
        currentInvoiceIdRef.current = response.id;
      }
      
      // Invoice is created as finalized (is_draft: false)
      // Backend automatically handles PDF generation and delivery on creation
      // No need for separate finalization call
      
      // Invalidate invoices query to show new invoice instantly
      // Use await to ensure invalidation completes before navigating
      await queryClient.invalidateQueries({ queryKey: ['accounting', 'invoices'] });
      
      // Also refetch to ensure immediate update
      await queryClient.refetchQueries({ queryKey: ['accounting', 'invoices'] });
      
      // Dynamic success message based on delivery method
      const messages = {
        'save_locally': 'Invoice saved successfully!',
        'send_invoice': 'Invoice sent successfully!',
        'request_payment': 'Payment request sent successfully!'
      } as const;
      toast.success(messages[deliveryMethod] || 'Invoice created successfully!');
      navigate('/accounting/invoices');
    },
  });


  // Auto-set issue date to today and generate invoice number on mount
  useEffect(() => {
    const today = new Date().toISOString().split('T')[0];
    updateField('issue_date', today);
    
    // Auto-generate invoice number: INV-YYYY-MMDD-XXX format
    // Industry standard: Prefix-Year-Date-Sequential
    const year = new Date().getFullYear();
    const month = String(new Date().getMonth() + 1).padStart(2, '0');
    const day = String(new Date().getDate()).padStart(2, '0');
    const random = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
    
    // Format: INV-2026-0115-347 (includes date for chronological tracking)
    const invoiceNumber = `INV-${year}-${month}${day}-${random}`;
    updateField('invoice_number', invoiceNumber);
  }, []);

  // Tax recommendations hook (only need setUserDefault for star toggle)
  const { setUserDefault } = useTaxRecommendations({
    propertyId: formData.property_id,
    category: 'rental',
  });

  // Track if form has been modified
  const [isDirty, setIsDirty] = useState(false);
  
  // Saved taxes modal
  const [isSavedTaxesModalOpen, setIsSavedTaxesModalOpen] = useState(false);
  
  // Prevent duplicate restore prompts
  const hasShownRestorePrompt = useRef(false);
  
  // Stripe Connect status for payment requests
  const { data: connectData, isLoading: isLoadingConnect } = useConnectStatus();
  
  // Mark as dirty whenever form data changes
  useEffect(() => {
    if (formData.invoice_number || lineItems.some(item => item.description)) {
      setIsDirty(true);
    }
  }, [formData, lineItems]);

  // Draft save functionality
  const saveDraft = useCallback(async (showToast = false): Promise<boolean> => {
    // Prevent concurrent saves
    if (isSavingRef.current) {
      console.log('⏭️ Skipping save - already in progress');
      return false;
    }
    
    isSavingRef.current = true;
    
    try {
      // Log current state for debugging
      console.log('💾 Starting save:', {
        currentInvoiceIdRef: currentInvoiceIdRef.current,
        urlId: id,
        invoiceNumber: formData.invoice_number,
        recipientType,
        recipientIds: {
          tenant_id: formData.tenant_id,
          ownership_entity_id: formData.ownership_entity_id,
          vendor_id: formData.vendor_id,
        },
        deliveryMethod,
        showToast
      });
      
      // Don't save if form is too empty
      if (!formData.invoice_number && lineItems.every(item => !item.description)) {
        return false;
      }

      // Filter out empty tax entries and deduplicate
      const validTaxes = formData.taxes?.filter(tax => {
        if (!tax.tax_name || !tax.tax_rate) return false;
        const rate = parseFloat(tax.tax_rate);
        return !isNaN(rate) && rate > 0;
      }).reduce((acc, tax) => {
        // Deduplicate by name + rate
        const key = `${tax.tax_name}_${parseFloat(tax.tax_rate)}`;
        const existing = acc.find(t => `${t.tax_name}_${parseFloat(t.tax_rate)}` === key);
        if (!existing) {
          acc.push(tax);
        }
        return acc;
      }, [] as typeof formData.taxes);

      // Prepare line items for submission
      const validLineItems = lineItems.map((item, index) => ({
        description: item.description,
        quantity: item.quantity,
        unit_price: item.unit_price,
        is_taxable: item.is_taxable,
        expense_category: item.expense_category || undefined,
        sort_order: index,
      }));

      const draftData: any = {
        invoice_number: formData.invoice_number,
        amount: calculatedTotals.grandTotal.toString(), // Required field
        description: formData.description || '', // Required field, empty string for drafts
        issue_date: formData.issue_date,
        due_date: formData.due_date || new Date().toISOString().split('T')[0], // Default to today if empty
        status: 'Draft',
        delivery_method: deliveryMethod, // Add delivery method
        property_id: formData.property_id && formData.property_id.toString().trim() 
          ? parseInt(formData.property_id.toString(), 10) 
          : undefined,
        line_items: validLineItems,
        taxes: validTaxes && validTaxes.length > 0 ? validTaxes : undefined,
        is_draft: true,
      };

      // Add recipient information based on type
      // Only include recipient_type if we have a valid recipient ID
      const tenantIdStr = formData.tenant_id?.toString().trim();
      const vendorIdStr = formData.vendor_id?.toString().trim();
      
      if (recipientType === 'tenant' && tenantIdStr && tenantIdStr !== '') {
        draftData.recipient_type = 'tenant';
        draftData.tenant_id = parseInt(tenantIdStr, 10);
      } else if (recipientType === 'ownership_entity' && formData.ownership_entity_id) {
        draftData.recipient_type = 'ownership_entity';
        draftData.ownership_entity_id = formData.ownership_entity_id;
      } else if (recipientType === 'vendor' && vendorIdStr && vendorIdStr !== '') {
        draftData.recipient_type = 'vendor';
        draftData.vendor_id = parseInt(vendorIdStr, 10);
      }

      // Log the full draft data being saved
      console.log('📤 Draft data to be saved:', {
        recipient_type: draftData.recipient_type,
        tenant_id: draftData.tenant_id,
        ownership_entity_id: draftData.ownership_entity_id,
        vendor_id: draftData.vendor_id,
        property_id: draftData.property_id,
        invoice_number: draftData.invoice_number,
        lineItemsCount: draftData.line_items?.length,
      });

      let response;
      // Use ref for reliable ID tracking (avoids race conditions with state updates)
      const existingId = currentInvoiceIdRef.current;
      
      if (existingId) {
        // Update existing draft
        response = await updateInvoice(existingId, draftData as UpdateInvoiceRequest);
        console.log('✅ Draft updated, response:', {
          id: response?.id,
          recipient_type: response?.recipient_type,
          tenant_id: response?.tenant_id,
          ownership_entity_id: response?.ownership_entity_id,
          vendor_id: response?.vendor_id,
        });
        if (showToast) toast.success('Draft updated successfully');
      } else {
        // Create new draft
        response = await createInvoice(draftData as CreateInvoiceRequest);
        console.log('✅ Draft created, response:', {
          id: response?.id,
          recipient_type: response?.recipient_type,
          tenant_id: response?.tenant_id,
          ownership_entity_id: response?.ownership_entity_id,
          vendor_id: response?.vendor_id,
        });
        if (response && response.id) {
          // Update ref immediately to prevent duplicate inserts on subsequent saves
          currentInvoiceIdRef.current = response.id;
          if (showToast) toast.success('Draft saved successfully');
        }
      }

      // Invalidate and refetch invoices query so the draft appears immediately in the table
      await queryClient.invalidateQueries({ queryKey: ['accounting', 'invoices'] });
      await queryClient.refetchQueries({ queryKey: ['accounting', 'invoices'] });
      
      setIsDirty(false);
      return true;
    } catch (error) {
      console.error('Draft save failed:', error);
      if (showToast) {
        toast.error('Failed to save draft');
      }
      return false;
    } finally {
      isSavingRef.current = false;
    }
  }, [formData, lineItems, recipientType, calculatedTotals, deliveryMethod, id]);

  // Auto-save to localStorage (no database hits)
  const LOCALSTORAGE_KEY = 'brikli_invoice_draft';
  
  useLocalStorageAutoSave({
    key: LOCALSTORAGE_KEY,
    data: {
      formData,
      lineItems,
      recipientType,
      deliveryMethod,
      calculatedTotals: {
        subtotal: calculatedTotals.subtotal.toString(),
        totalTax: calculatedTotals.totalTax.toString(),
        grandTotal: calculatedTotals.grandTotal.toString(),
      },
    },
    enabled: isDirty && calculatedTotals.grandTotal.toNumber() > 0,
    delay: 10000, // 10 seconds
  });

  // Manual save handler (for "Save as Draft" button) - Creates explicit database draft
  const handleSaveAsDraft = useCallback(async () => {
    const success = await saveDraft(true); // Show toast notification
    if (success) {
      // Clear localStorage after successfully saving to database
      clearLocalStorage(LOCALSTORAGE_KEY);
      // Navigate back to invoices list
      navigate('/accounting/invoices');
    }
  }, [saveDraft, navigate]);

  // Warn about unsaved changes
  useUnsavedChangesWarning(isDirty && !isSubmitting);

  // Load initial data and check for unsaved work in localStorage
  useEffect(() => {
    loadInitialData();
    
    // Only check for unsaved work if creating a new invoice (no ID in URL)
    if (!id) {
      checkForUnsavedWork();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run only once on mount
  
  // Load delivery method when editing an existing invoice
  useEffect(() => {
    const loadDeliveryMethod = async () => {
      if (id) {
        try {
          const invoice = await fetchInvoice(parseInt(id));
          if (invoice.delivery_method) {
            setDeliveryMethod(invoice.delivery_method);
          }
        } catch (error) {
          console.error('Failed to load delivery method:', error);
        }
      }
    };
    
    loadDeliveryMethod();
  }, [id]);

  const checkForUnsavedWork = () => {
    // Prevent duplicate prompts (React 18 Strict Mode runs effects twice in dev)
    if (hasShownRestorePrompt.current) {
      return;
    }
    
    const { data: savedData, timestamp } = loadFromLocalStorage<any>(LOCALSTORAGE_KEY);
    
    if (!savedData || !timestamp) return;
    
    // Check if saved data is recent (within last 7 days)
    const savedDate = new Date(timestamp);
    const hoursSinceSave = (Date.now() - savedDate.getTime()) / (1000 * 60 * 60);
    
    if (hoursSinceSave > 24 * 7) {
      // Too old, clear it
      clearLocalStorage(LOCALSTORAGE_KEY);
      return;
    }
    
    // Mark that we've shown the prompt
    hasShownRestorePrompt.current = true;
    
    // Show restore prompt
    const toastId = toast.info(
      <div>
        <p className="font-medium">Unsaved work found</p>
        <p className="text-sm mt-1">
          You have unsaved changes from {savedDate.toLocaleString()}
        </p>
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => {
              // Restore the data
              if (savedData.formData) {
                Object.keys(savedData.formData).forEach(key => {
                  updateField(key as any, savedData.formData[key]);
                });
              }
              if (savedData.lineItems) {
                // Note: This requires exposing setLineItems from useInvoiceForm
                // For now, user will need to re-enter line items
              }
              if (savedData.recipientType) {
                setRecipientType(savedData.recipientType);
              }
              if (savedData.deliveryMethod) {
                setDeliveryMethod(savedData.deliveryMethod);
              }
              
              toast.success('Restored unsaved work');
              toast.dismiss(toastId);
            }}
            className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
          >
            Restore
          </button>
          <button
            onClick={() => {
              clearLocalStorage(LOCALSTORAGE_KEY);
              toast.dismiss(toastId);
            }}
            className="px-3 py-1 bg-gray-200 text-gray-800 rounded text-sm hover:bg-gray-300"
          >
            Discard
          </button>
        </div>
      </div>,
      {
        autoClose: false,
        closeButton: false,
        position: 'top-center',
      }
    );
  };

  const loadInitialData = async () => {
    try {
      const [propertiesData, tenantsData, entitiesData, vendorsData] = await Promise.all([
        fetchProperties(),
        fetchTenants(),
        fetchOwnershipEntities(),
        listVendors(),
      ]);
      
      setProperties(propertiesData || []);
      setTenants(tenantsData || []);
      // Handle response structure for ownership entities and vendors
      setOwnershipEntities(entitiesData?.entities || []);
      setVendors((vendorsData as any)?.vendors || []);
      
      // Note: userFavoriteTaxes are loaded by useInvoiceForm hook automatically
    } catch (error) {
      console.error('Failed to load data:', error);
      toast.error('Failed to load form data');
    }
  };

  const handleSubmit = useCallback(async () => {
    try {
      const success = await submitForm();
      if (success) {
        setIsDirty(false);
        // Clear localStorage when invoice is created
        clearLocalStorage(LOCALSTORAGE_KEY);
        // Note: Finalization and navigation are handled in onSuccess callback
      }
    } catch (error) {
      // Error is already handled by submitForm
      console.error('Submit failed:', error);
    }
  }, [submitForm]);

  const handleCancel = () => {
    if (isDirty) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to cancel?'
      );
      if (!confirmed) return;
      
      // Clear localStorage when cancelling
      clearLocalStorage(LOCALSTORAGE_KEY);
    }
    navigate('/accounting/invoices');
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd + S: Save draft
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSaveAsDraft();
      }
      
      // Ctrl/Cmd + Enter: Submit form
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (!isSubmitting) {
          handleSubmit();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSaveAsDraft, handleSubmit, isSubmitting]);

  // Handle star button for saving/removing saved taxes
  const handleSetTaxDefault = async (tax: TaxDetail) => {
    if (!tax.tax_name || !tax.tax_rate) {
      toast.error("Please enter both tax name and rate before saving.");
      return;
    }

    const rate = Number.parseFloat(tax.tax_rate);
    if (isNaN(rate) || rate <= 0 || rate > 100) {
      toast.error("Please enter a valid tax rate between 0.01% and 100%.");
      return;
    }

    // Check if this tax is currently saved
    const isCurrentlySaved = isCurrentDefault(tax);
    
    if (isCurrentlySaved) {
      // Remove from saved taxes
      const taxData = {
        tax_name: tax.tax_name.trim(),
        tax_rate: rate.toString()
      };

      const result = await removeUserTaxDefault(taxData);
      
      if (result.success) {
        // Get fresh list from API to update state
        const updatedSavedTaxes = await getUserTaxDefault();
        setUserFavoriteTaxes(updatedSavedTaxes);
        toast.success(`Removed ${tax.tax_name} from saved taxes`);
      } else {
        toast.error(result.error || 'Failed to remove tax');
      }
    } else {
      // Add to saved taxes
      const taxData = {
        tax_name: tax.tax_name.trim(),
        tax_rate: rate.toString()
      };

      const success = await setUserDefault(taxData);
      
      if (success) {
        // Get fresh list from API to update state and show in toast
        const updatedSavedTaxes = await getUserTaxDefault();
        
        // Update the state with the fresh list
        setUserFavoriteTaxes(updatedSavedTaxes);
        
        // Show toast with all saved taxes
        const taxList = updatedSavedTaxes.map(t => `${t.tax_name} (${t.tax_rate}%)`).join(', ');
        toast.success(`⭐ Saved! Your saved taxes: ${taxList}`);
      }
    }
  };

  // Check if a tax is currently in the user's saved taxes
  const isCurrentDefault = (tax: TaxDetail): boolean => {
    if (!tax.tax_name || !tax.tax_rate) return false;
    
    // Check if this tax is in the user's saved taxes list
    // Normalize tax rates by parsing as numbers to handle "13" vs "13.00"
    const taxRate = parseFloat(tax.tax_rate);
    if (isNaN(taxRate)) return false;
    
    console.log('Checking tax:', { 
      taxName: tax.tax_name, 
      taxRate: tax.tax_rate,
      parsedRate: taxRate,
      userFavoriteTaxes: userFavoriteTaxes.map(t => ({ name: t.tax_name, rate: t.tax_rate }))
    });
    
    const result = userFavoriteTaxes.some(savedTax => {
      const savedRate = parseFloat(savedTax.tax_rate);
      const matches = savedTax.tax_name === tax.tax_name && 
             !isNaN(savedRate) && 
             Math.abs(savedRate - taxRate) < 0.001;
      
      console.log('Comparing with saved tax:', {
        savedName: savedTax.tax_name,
        savedRate: savedTax.tax_rate,
        parsedSavedRate: savedRate,
        nameMatches: savedTax.tax_name === tax.tax_name,
        rateMatches: Math.abs(savedRate - taxRate) < 0.001,
        matches
      });
      
      return matches;
    });
    
    console.log('isCurrentDefault result:', result);
    return result;
  };

  // Get tooltip text for star button
  const getTooltipText = (tax: TaxDetail): string => {
    if (!tax.tax_name || !tax.tax_rate) return "Add to my saved taxes";
    
    if (isCurrentDefault(tax)) {
      return "⭐ This is one of your saved taxes! Click to remove.";
    }
    
    return "Add to my saved taxes";
  };

  const getRecipientInfo = () => {
    if (recipientType === 'tenant' && formData.tenant_id) {
      const tenant = tenants.find(t => t.id === parseInt(formData.tenant_id));
      return {
        name: tenant?.company_name || `${tenant?.first_name || ''} ${tenant?.last_name || ''}`.trim(),
        email: tenant?.email || '',
      };
    }
    if (recipientType === 'ownership_entity' && formData.ownership_entity_id) {
      const entity = ownershipEntities.find((e: any) => e.id === formData.ownership_entity_id);
      return {
        name: entity?.name || '',
        email: entity?.contact_email || '',
      };
    }
    if (recipientType === 'vendor' && formData.vendor_id) {
      const vendor = vendors.find((v: any) => v.id === parseInt(formData.vendor_id || '0'));
      return {
        name: vendor?.company_name || '',
        email: vendor?.email || '',
      };
    }
    return null;
  };

  return (
    <div className="fixed inset-0 top-16 flex flex-col bg-gray-50 dark:bg-gray-900">
      {/* Action Bar - Flush at top */}
      <div className="flex-shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 py-3 px-6">
        <div className="flex items-center justify-between gap-6">
          {/* Left: Delivery Option Selector */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Invoice Delivery:
            </label>
            <div className="flex gap-2 bg-gray-100 dark:bg-gray-700 p-1 rounded-lg">
              <Tooltip 
                content={
                  <div>
                    <p className="font-semibold mb-1">Save Locally</p>
                    <p className="text-xs opacity-90">Invoice is saved in your system but not sent to the recipient. Use for record keeping or when you'll deliver manually.</p>
                  </div>
                }
                position="bottom"
              >
                <button
                  onClick={() => setDeliveryMethod('save_locally')}
                  className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${
                    deliveryMethod === 'save_locally'
                      ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                  }`}
                >
                  <i className="fas fa-save mr-2" />
                  Save Locally
                </button>
              </Tooltip>
              
              <Tooltip 
                content={
                  <div>
                    <p className="font-semibold mb-1">Send Invoice Only</p>
                    <p className="text-xs opacity-90">Sends a branded PDF invoice via email. Recipient can view and download the invoice, but must pay through other means (check, e-transfer, etc.).</p>
                  </div>
                }
                position="bottom"
              >
                <button
                  onClick={() => setDeliveryMethod('send_invoice')}
                  className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${
                    deliveryMethod === 'send_invoice'
                      ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                  }`}
                >
                  <i className="fas fa-envelope mr-2" />
                  Send Invoice Only
                </button>
              </Tooltip>
              
              <Tooltip 
                content={
                  <div>
                    <p className="font-semibold mb-1">Request Payment</p>
                    {!isLoadingConnect && connectData && !connectData.charges_enabled ? (
                      <div>
                        <p className="text-xs opacity-90 mb-2">Creates a Stripe invoice with an online payment link. Recipient can pay instantly with credit card or bank transfer.</p>
                        <div className="pt-2 border-t border-yellow-500/30">
                          <p className="text-xs font-semibold text-yellow-300 mb-1">🔒 Stripe Connect Required</p>
                          <p className="text-xs opacity-90">
                            You need to connect your Stripe account first. Visit <span className="underline">Integrations</span> to set up Stripe Connect.
                          </p>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs opacity-90">Creates a Stripe invoice with an online payment link. Recipient can pay instantly with credit card or bank transfer.</p>
                    )}
                  </div>
                }
                position="bottom"
              >
                <button
                  onClick={() => {
                    if (!isLoadingConnect && connectData && connectData.charges_enabled) {
                      setDeliveryMethod('request_payment');
                    }
                  }}
                  disabled={!isLoadingConnect && connectData && !connectData.charges_enabled}
                  className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all relative ${
                    deliveryMethod === 'request_payment'
                      ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                      : !isLoadingConnect && connectData && !connectData.charges_enabled
                      ? 'text-gray-400 dark:text-gray-600 cursor-not-allowed opacity-60'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                  }`}
                >
                  {!isLoadingConnect && connectData && !connectData.charges_enabled ? (
                    <i className="fas fa-lock mr-2" />
                  ) : (
                    <i className="fas fa-credit-card mr-2" />
                  )}
                  Request Payment
                </button>
              </Tooltip>
            </div>
          </div>

          {/* Right: Action Buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleCancel}
              disabled={isSubmitting}
              className="px-6 py-2.5 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            
            <button
              onClick={handleSaveAsDraft}
              disabled={isSubmitting || !isDirty}
              className="px-6 py-2.5 bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              Save as Draft
            </button>
            
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="px-6 py-2.5 bg-[#004225] hover:bg-[#016231] text-white rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  {deliveryMethod === 'save_locally' ? 'Create Invoice' : deliveryMethod === 'send_invoice' ? 'Send Invoice' : 'Request Payment'}
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Main Content - Two Column Layout with proper scroll */}
      <div className="flex-1 overflow-hidden">
        <FinancialErrorBoundary>
          <div className="h-full grid grid-cols-1 lg:grid-cols-2 gap-0">
            {/* Left Column - Form (Scrollable) */}
            <div className="overflow-y-auto bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
              <div className="space-y-6 px-6 py-6">
                {/* Invoice Recipient - Moved to top */}
                <div>
                <RecipientSelector
                  recipientType={recipientType}
                  onRecipientTypeChange={setRecipientType}
                  tenants={tenants}
                  ownershipEntities={ownershipEntities}
                  vendors={vendors}
                  properties={properties}
                  selectedTenantId={formData.tenant_id && formData.tenant_id.trim() ? formData.tenant_id : null}
                  selectedOwnershipEntityId={formData.ownership_entity_id || null}
                  selectedVendorId={formData.vendor_id && formData.vendor_id.trim() ? formData.vendor_id : null}
                  onTenantChange={(id) => updateField('tenant_id', id ? String(id) : '')}
                  onOwnershipEntityChange={(id) => updateField('ownership_entity_id', id || undefined)}
                  onVendorChange={(id) => updateField('vendor_id', id ? String(id) : '')}
                  onPropertyChange={(id) => updateField('property_id', id ? String(id) : '')}
                  propertyId={formData.property_id && String(formData.property_id).trim() ? String(formData.property_id) : null}
                  errors={errors}
                />
              </div>

              {/* Invoice Details - Compact */}
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                  Invoice Details
                </h2>
                
                <div className="grid grid-cols-2 gap-3">
                  {/* Invoice Number - Auto-generated */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Invoice Number
                    </label>
                    <input
                      type="text"
                      value={formData.invoice_number}
                      onChange={(e) => updateField('invoice_number', e.target.value)}
                      className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-[#004225] focus:border-transparent"
                    />
                    {errors.invoice_number && (
                      <p className="mt-1 text-sm text-red-500">{errors.invoice_number}</p>
                    )}
                  </div>

                  {/* Due Date */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Due Date *
                    </label>
                    <input
                      type="date"
                      value={formData.due_date}
                      onChange={(e) => updateField('due_date', e.target.value)}
                      className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-[#004225] focus:border-transparent"
                    />
                    {errors.due_date && (
                      <p className="mt-1 text-sm text-red-500">{errors.due_date}</p>
                    )}
                  </div>
                </div>
                </div>

                {/* Line Items */}
                <div>
                <LineItemsManager
                  lineItems={lineItems}
                  onAddLineItem={addLineItem}
                  onRemoveLineItem={removeLineItem}
                  onUpdateLineItem={updateLineItem}
                  errors={errors}
                />
              </div>
                {/* Taxes */}
                <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Taxes
                  </h2>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setIsSavedTaxesModalOpen(true)}
                      className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white font-medium flex items-center gap-1"
                    >
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                      View Saved
                    </button>
                    <button
                      onClick={addTaxLine}
                      className="text-sm text-[#004225] hover:text-[#016231] font-medium"
                    >
                      + Add Tax
                    </button>
                  </div>
                </div>
                
                <div className="space-y-3">
                  {formData.taxes?.map((tax, index) => (
                    <div key={index} className="flex gap-3 items-center">
                      <input
                        type="text"
                        placeholder="Tax name (e.g., GST)"
                        value={tax.tax_name}
                        onChange={(e) => updateTaxLine(index, 'tax_name', e.target.value)}
                        className="flex-1 px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-[#004225] focus:border-transparent"
                      />
                      <input
                        type="number"
                        placeholder="Rate %"
                        value={tax.tax_rate}
                        onChange={(e) => updateTaxLine(index, 'tax_rate', e.target.value)}
                        className="w-24 px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-[#004225] focus:border-transparent"
                      />
                      
                      {/* Star Button for Setting Default */}
                      <button
                        type="button"
                        onClick={() => handleSetTaxDefault({ tax_name: tax.tax_name, tax_rate: String(tax.tax_rate) })}
                        disabled={!tax.tax_name || !tax.tax_rate}
                        className={`p-2 h-9 w-9 flex items-center justify-center border rounded-lg transition-all ${
                          isCurrentDefault({ tax_name: tax.tax_name, tax_rate: String(tax.tax_rate) })
                            ? 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400 border-yellow-200 dark:border-yellow-700 hover:bg-yellow-100 dark:hover:bg-yellow-900/50'
                            : 'bg-white dark:bg-gray-700 text-gray-400 dark:text-gray-500 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 hover:text-yellow-500 dark:hover:text-yellow-400 disabled:opacity-50 disabled:cursor-not-allowed'
                        }`}
                        title={getTooltipText({ tax_name: tax.tax_name, tax_rate: String(tax.tax_rate) })}
                      >
                        <Star 
                          className="w-4 h-4" 
                          fill={isCurrentDefault({ tax_name: tax.tax_name, tax_rate: String(tax.tax_rate) }) ? "currentColor" : "none"}
                        />
                      </button>

                      {formData.taxes && formData.taxes.length > 1 && (
                        <button
                          onClick={() => removeTaxLine(index)}
                          className="px-3 py-2 text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                        >
                          <X className="w-5 h-5" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Invoice Description */}
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                  Notes
                </h2>
                
                <textarea
                  placeholder="Add notes or description for this invoice..."
                  value={formData.description}
                  onChange={(e) => updateField('description', e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-[#004225] focus:border-transparent resize-none"
                />
                </div>
              </div>
            </div>

            {/* Right Column - Live Preview (Scrollable) */}
            <div className="overflow-y-auto bg-gray-50 dark:bg-gray-900">
              <div className="px-6 py-6">
                <div className="sticky top-0">
                  <InvoicePreview
                  formData={formData}
                  lineItems={lineItems}
                  calculatedTotals={calculatedTotals}
                  recipientName={getRecipientInfo()?.name}
                  recipientEmail={getRecipientInfo()?.email}
                  companyName="Brikli"
                />
                </div>
              </div>
            </div>
          </div>
        </FinancialErrorBoundary>
      </div>

      {/* Saved Taxes Modal */}
      <SavedTaxesModal
        isOpen={isSavedTaxesModalOpen}
        onClose={() => setIsSavedTaxesModalOpen(false)}
        savedTaxes={userFavoriteTaxes}
        onTaxesUpdated={async () => {
          const updated = await getUserTaxDefault();
          setUserFavoriteTaxes(updated);
        }}
        onApplyTax={(tax) => {
          // Check if tax already exists in the form
          const existingTax = formData.taxes.find(
            t => t.tax_name === tax.tax_name && 
                 parseFloat(t.tax_rate) === parseFloat(tax.tax_rate)
          );
          
          if (existingTax) {
            toast.info(`${tax.tax_name} is already applied to this invoice`);
            return;
          }
          
          // Add the tax to the invoice
          const currentTaxes = formData.taxes || [];
          
          // If there's only one empty tax line, replace it
          if (currentTaxes.length === 1 && !currentTaxes[0].tax_name && !currentTaxes[0].tax_rate) {
            updateField('taxes', [{
              tax_name: tax.tax_name,
              tax_rate: tax.tax_rate,
            }]);
          } else {
            // Otherwise, add as a new tax line
            updateField('taxes', [
              ...currentTaxes,
              {
                tax_name: tax.tax_name,
                tax_rate: tax.tax_rate,
              }
            ]);
          }
        }}
      />
    </div>
  );
};

export default InvoiceCreatePage;

import { useState, useCallback, useMemo, useEffect } from 'react';
import { toast } from 'react-toastify';
import Decimal from 'decimal.js';
import { createInvoice, updateInvoice, getUserTaxDefault, clearUserTaxDefault, fetchInvoice } from '../../utils/api/accounting';
import type { 
  InvoiceFormData, 
  CreateInvoiceRequest, 
  UpdateInvoiceRequest,
  TaxDetail,
  InvoiceStatus,
  InvoiceLineItem,
  RecipientType,
  Invoice
} from '../../types/accounting';
import { reportError, reportWarning } from '../../utils/error-reporting';

interface UseInvoiceFormProps {
  initialData?: Partial<InvoiceFormData>;
  mode?: 'create' | 'edit';
  invoiceId?: number;
  deliveryMethod?: 'save_locally' | 'send_invoice' | 'request_payment';
  onSuccess?: (response?: Invoice) => void;
}

interface InvoiceFormState {
  formData: InvoiceFormData;
  lineItems: InvoiceLineItem[];
  recipientType: RecipientType | null;
  errors: Record<string, string>;
  isSubmitting: boolean;
  calculatedTotals: {
    subtotal: Decimal;
    taxableSubtotal: Decimal;
    nonTaxableSubtotal: Decimal;
    totalTax: Decimal;
    grandTotal: Decimal;
  };
  isUserDefaultTax: boolean;
  userFavoriteTaxes: TaxDetail[];
}

interface InvoiceFormActions {
  updateField: <K extends keyof InvoiceFormData>(field: K, value: InvoiceFormData[K]) => void;
  updateTaxes: (taxes: TaxDetail[]) => void;
  addTaxLine: () => void;
  removeTaxLine: (index: number) => void;
  updateTaxLine: (index: number, field: keyof TaxDetail, value: string) => void;
  // Line items management
  addLineItem: () => void;
  removeLineItem: (index: number) => void;
  updateLineItem: (index: number, field: keyof InvoiceLineItem, value: string | boolean | number) => void;
  setRecipientType: (type: RecipientType | null) => void;
  setLineItems: (items: InvoiceLineItem[]) => void;
  // Form management
  validateForm: () => boolean;
  submitForm: () => Promise<boolean>;
  resetForm: () => void;
  setFormData: (data: Partial<InvoiceFormData>) => void;
  clearUserTaxDefaultFromForm: () => Promise<void>;
  setIsUserDefaultTax: (isDefault: boolean) => void;
  setUserFavoriteTaxes: (taxes: TaxDetail[]) => void;
  loadUserTaxDefault: (preloadIntoForm?: boolean) => Promise<void>;
}

const createInitialFormData = (): InvoiceFormData => ({
  invoice_number: "",
  amount: "",
  description: "",
  issue_date: new Date().toISOString().split("T")[0],
  due_date: "",
  status: "Pending" as InvoiceStatus,
  property_id: "",
  property_name: "",
  tenant_id: "",
  tenant_name: "",
  line_items: [{
    description: '',
    quantity: '1',
    unit_price: '0.00',
    is_taxable: true,
    sort_order: 0,
  }],
  taxes: [{ tax_name: "", tax_rate: "" }],
});

export const useInvoiceForm = ({ 
  initialData, 
  mode = 'create',
  invoiceId,
  deliveryMethod = 'save_locally',
  onSuccess 
}: UseInvoiceFormProps): InvoiceFormState & InvoiceFormActions => {
  const [formData, setFormDataState] = useState<InvoiceFormData>(() => ({
    ...createInitialFormData(),
    ...initialData,
  }));
  
  const [lineItems, setLineItems] = useState<InvoiceLineItem[]>([{
    description: '',
    quantity: '1',
    unit_price: '0.00',
    line_total: '0.00',
    is_taxable: true,
    expense_category: '',
    sort_order: 0,
  }]);
  
  const [recipientType, setRecipientType] = useState<RecipientType | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUserDefaultTax, setIsUserDefaultTax] = useState(false);
  const [userFavoriteTaxes, setUserFavoriteTaxes] = useState<TaxDetail[]>([]);  
  // Load existing invoice data when in edit mode
  useEffect(() => {
    const loadInvoiceData = async () => {
      if (mode === 'edit' && invoiceId) {
        try {
          const invoice = await fetchInvoice(invoiceId);
          
          // Populate form data
          setFormDataState({
            id: invoice.id.toString(),
            invoice_number: invoice.invoice_number || '',
            amount: invoice.amount || '0',
            description: invoice.description || '',
            issue_date: invoice.issue_date ? invoice.issue_date.split('T')[0] : '',
            due_date: invoice.due_date ? invoice.due_date.split('T')[0] : '',
            status: invoice.status as InvoiceStatus,
            property_id: invoice.property_id?.toString() || '',
            property_name: invoice.property?.name || '',
            tenant_id: invoice.tenant_id?.toString() || '',
            tenant_name: invoice.tenant?.full_name || '',
            ownership_entity_id: invoice.ownership_entity_id,
            ownership_entity_name: '',
            vendor_id: invoice.vendor_id?.toString() || '',
            vendor_name: '',
            line_items: [], // Handled separately
            taxes: invoice.taxes && invoice.taxes.length > 0 
              ? invoice.taxes.map(tax => ({
                  tax_name: tax.tax_name,
                  tax_rate: tax.tax_rate,
                }))
              : [{ tax_name: '', tax_rate: '' }],
          });
          
          // Populate line items
          if (invoice.line_items && invoice.line_items.length > 0) {
            setLineItems(invoice.line_items.map((item, index) => ({
              id: item.id,
              description: item.description || '',
              quantity: item.quantity || '1',
              unit_price: item.unit_price || '0.00',
              line_total: item.line_total || '0.00',
              is_taxable: item.is_taxable ?? true,
              expense_category: item.expense_category || '',
              sort_order: item.sort_order ?? index,
            })));
          }
          
          // Set recipient type
          if (invoice.recipient_type) {
            setRecipientType(invoice.recipient_type);
          }
        } catch (error) {
          console.error('Failed to load invoice:', error);
          toast.error('Failed to load invoice');
        }
      }
    };
    
    loadInvoiceData();
  }, [mode, invoiceId]);
  
  const loadUserTaxDefault = useCallback(async (preloadIntoForm: boolean = true) => {
    try {
      const userTaxDefaults = await getUserTaxDefault();
      if (userTaxDefaults && userTaxDefaults.length > 0) {
        // Store the full list of favorite taxes
        setUserFavoriteTaxes(userTaxDefaults);
        
        // Only preload into form if requested (e.g., on initial load)
        if (preloadIntoForm) {
          setFormDataState(prev => ({
            ...prev,
            taxes: userTaxDefaults.map(tax => ({
              tax_name: tax.tax_name,
              tax_rate: tax.tax_rate,
            })),
          }));
        }
        
        setIsUserDefaultTax(true);
      }
    } catch (error) {
      // Silently fail - user just won't get pre-populated tax defaults
      console.log('No user tax default found or error loading:', error);
    }
  }, []);

  // Load user's favorite taxes list
  useEffect(() => {
    if (mode === 'create' && !initialData?.taxes) {
      // For new invoices, load and preload into form
      loadUserTaxDefault(true);
    } else if (mode === 'edit') {
      // For editing, just load the favorites list (don't overwrite invoice taxes)
      loadUserTaxDefault(false);
    }
  }, [mode, initialData, loadUserTaxDefault]);

  // Calculate totals based on line items
  const calculatedTotals = useMemo(() => {
    // Calculate subtotal from line items
    const subtotal = lineItems.reduce((acc, item) => {
      try {
        const quantity = new Decimal(item.quantity || 0);
        const unitPrice = new Decimal(item.unit_price || 0);
        const lineTotal = quantity.mul(unitPrice);
        return acc.add(lineTotal);
      } catch {
        return acc;
      }
    }, new Decimal(0));
    
    // Calculate taxable subtotal (only from taxable line items)
    const taxableSubtotal = lineItems.reduce((acc, item) => {
      if (!item.is_taxable) return acc;
      try {
        const quantity = new Decimal(item.quantity || 0);
        const unitPrice = new Decimal(item.unit_price || 0);
        const lineTotal = quantity.mul(unitPrice);
        return acc.add(lineTotal);
      } catch {
        return acc;
      }
    }, new Decimal(0));
    
    // Calculate non-taxable subtotal (for transparency)
    const nonTaxableSubtotal = lineItems.reduce((acc, item) => {
      if (item.is_taxable) return acc;
      try {
        const quantity = new Decimal(item.quantity || 0);
        const unitPrice = new Decimal(item.unit_price || 0);
        const lineTotal = quantity.mul(unitPrice);
        return acc.add(lineTotal);
      } catch {
        return acc;
      }
    }, new Decimal(0));
    
    // Calculate taxes on taxable items only
    const totalTax = formData.taxes.reduce((acc, tax) => {
      if (tax.tax_name && tax.tax_rate) {
        const rate = new Decimal(tax.tax_rate);
        const taxAmount = taxableSubtotal.mul(rate).div(100);
        return acc.add(taxAmount);
      }
      return acc;
    }, new Decimal(0));

    const grandTotal = subtotal.add(totalTax);

    return {
      subtotal,
      taxableSubtotal,
      nonTaxableSubtotal,
      totalTax,
      grandTotal,
    };
  }, [lineItems, formData.taxes]);

  const updateField = useCallback(<K extends keyof InvoiceFormData>(
    field: K, 
    value: InvoiceFormData[K]
  ) => {
    setFormDataState(prev => ({
      ...prev,
      [field]: value,
    }));

    // Clear field error when user starts typing
    if (errors[field as string]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[field as string];
        return newErrors;
      });
    }
  }, [errors]);

  const setFormData = useCallback((data: Partial<InvoiceFormData>) => {
    setFormDataState(prev => ({
      ...prev,
      ...data,
    }));
  }, []);

  const updateTaxes = useCallback((taxes: TaxDetail[]) => {
    setFormDataState(prev => ({
      ...prev,
      taxes: taxes.length > 0 ? taxes : [{ tax_name: "", tax_rate: "" }],
    }));
  }, []);

  const addTaxLine = useCallback(() => {
    setFormDataState(prev => ({
      ...prev,
      taxes: [...prev.taxes, { tax_name: "", tax_rate: "" }],
    }));
  }, []);

  const removeTaxLine = useCallback((index: number) => {
    setFormDataState(prev => ({
      ...prev,
      taxes: prev.taxes.length > 1 
        ? prev.taxes.filter((_, i) => i !== index)
        : prev.taxes, // Keep at least one tax line
    }));
  }, []);

  const updateTaxLine = useCallback((
    index: number, 
    field: keyof TaxDetail, 
    value: string
  ) => {
    setFormDataState(prev => ({
      ...prev,
      taxes: prev.taxes.map((tax, i) => 
        i === index ? { ...tax, [field]: value } : tax
      ),
    }));
  }, []);

  // Line items management
  const addLineItem = useCallback(() => {
    setLineItems(prev => [
      ...prev,
      {
        description: '',
        quantity: '1',
        unit_price: '0.00',
        line_total: '0.00',
        is_taxable: true,
        expense_category: '',
        sort_order: prev.length,
      }
    ]);
  }, []);

  const removeLineItem = useCallback((index: number) => {
    setLineItems(prev => {
      if (prev.length <= 1) return prev; // Keep at least one line item
      return prev.filter((_, i) => i !== index).map((item, i) => ({
        ...item,
        sort_order: i,
      }));
    });
  }, []);

  const updateLineItem = useCallback((
    index: number,
    field: keyof InvoiceLineItem,
    value: string | boolean | number
  ) => {
    setLineItems(prev => prev.map((item, i) => {
      if (i !== index) return item;
      
      const updated = { ...item, [field]: value };
      
      // Auto-calculate line_total when quantity or unit_price changes
      if (field === 'quantity' || field === 'unit_price') {
        try {
          const quantity = new Decimal(field === 'quantity' ? String(value) : item.quantity || '0');
          const unitPrice = new Decimal(field === 'unit_price' ? String(value) : item.unit_price || '0');
          updated.line_total = quantity.mul(unitPrice).toFixed(2);
        } catch {
          updated.line_total = '0.00';
        }
      }
      
      return updated;
    }));
    
    // Clear field error when user starts typing
    if (errors[`line_item_${index}_${field}`]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[`line_item_${index}_${field}`];
        return newErrors;
      });
    }
  }, [errors]);

  const validateForm = useCallback((): boolean => {
    const newErrors: Record<string, string> = {};

    // Required field validations
    if (!formData.invoice_number?.trim()) {
      newErrors.invoice_number = 'Invoice number is required';
    }

    if (!formData.issue_date) {
      newErrors.issue_date = 'Issue date is required';
    }

    if (!formData.due_date) {
      newErrors.due_date = 'Due date is required';
    }

    // Date validation
    if (formData.issue_date && formData.due_date) {
      const issueDate = new Date(formData.issue_date);
      const dueDate = new Date(formData.due_date);
      
      if (dueDate < issueDate) {
        newErrors.due_date = 'Due date cannot be before issue date';
      }
    }

    // Line items validation
    if (lineItems.length === 0) {
      newErrors.line_items = 'At least one line item is required';
    } else {
      lineItems.forEach((item, index) => {
        if (!item.description?.trim()) {
          newErrors[`line_item_${index}_description`] = 'Description is required';
        }

        const quantity = parseFloat(item.quantity || '0');
        if (isNaN(quantity) || quantity <= 0) {
          newErrors[`line_item_${index}_quantity`] = 'Quantity must be greater than 0';
        }

        const unitPrice = parseFloat(item.unit_price || '0');
        if (isNaN(unitPrice) || unitPrice < 0) {
          newErrors[`line_item_${index}_unit_price`] = 'Unit price must be non-negative';
        }
      });
    }

    // Recipient validation (optional but if specified, must be valid)
    if (recipientType === 'tenant' && !formData.tenant_id) {
      newErrors.tenant_id = 'Please select a tenant';
    }
    if (recipientType === 'ownership_entity' && !formData.ownership_entity_id) {
      newErrors.ownership_entity_id = 'Please select an ownership entity';
    }
    if (recipientType === 'vendor' && !formData.vendor_id) {
      newErrors.vendor_id = 'Please select a vendor';
    }

    // Tax validation  
    formData.taxes.forEach((tax, index) => {
      if (tax.tax_name && !tax.tax_rate) {
        newErrors[`tax_rate_${index}`] = 'Tax rate is required';
      }
      
      if (tax.tax_rate && (!tax.tax_name || !tax.tax_name.trim())) {
        newErrors[`tax_name_${index}`] = 'Tax name is required';
      }

      if (tax.tax_rate) {
        const rate = parseFloat(tax.tax_rate);
        if (isNaN(rate) || rate < 0 || rate > 100) {
          newErrors[`tax_rate_${index}`] = 'Tax rate must be between 0% and 100%';
        }
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formData, lineItems, recipientType]);

  const submitForm = useCallback(async (): Promise<boolean> => {
    if (!validateForm()) {
      toast.error('Please fix the form errors before submitting');
      return false;
    }

    setIsSubmitting(true);

    try {
      // Filter out empty tax entries
      const validTaxes = formData.taxes.filter(tax => {
        if (!tax.tax_name || !tax.tax_rate) return false;
        const rate = parseFloat(tax.tax_rate);
        return !isNaN(rate) && rate > 0;
      });

      // Prepare line items for submission
      const validLineItems = lineItems.map((item, index) => ({
        description: item.description,
        quantity: item.quantity,
        unit_price: item.unit_price,
        is_taxable: item.is_taxable,
        expense_category: item.expense_category || undefined,
        sort_order: index,
      }));

      const submitData: Partial<CreateInvoiceRequest> & Partial<UpdateInvoiceRequest> = {
        invoice_number: formData.invoice_number,
        amount: calculatedTotals.grandTotal.toString(), // REQUIRED: grand total (subtotal + taxes)
        description: formData.description?.trim() || '', // REQUIRED: backend auto-generates if empty
        issue_date: formData.issue_date,
        due_date: formData.due_date,
        status: formData.status,
        delivery_method: deliveryMethod, // Delivery method for invoice (save locally / send email / request payment)
        is_draft: false, // Create as finalized invoice (not draft) - backend will handle PDF generation and delivery
        property_id: formData.property_id && formData.property_id.toString().trim() ? parseInt(formData.property_id.toString(), 10) : undefined,
        line_items: validLineItems,
        taxes: validTaxes.length > 0 ? validTaxes : undefined,
      };

      // Add recipient information based on type
      if (recipientType) {
        submitData.recipient_type = recipientType;
        
        if (recipientType === 'tenant' && formData.tenant_id) {
          submitData.tenant_id = parseInt(formData.tenant_id.toString(), 10);
        } else if (recipientType === 'ownership_entity' && formData.ownership_entity_id) {
          submitData.ownership_entity_id = formData.ownership_entity_id;
        } else if (recipientType === 'vendor' && formData.vendor_id) {
          submitData.vendor_id = parseInt(formData.vendor_id.toString(), 10);
        }
      }

      let response: Invoice;
      if (mode === 'create') {
        response = await createInvoice(submitData as CreateInvoiceRequest);
      } else {
        if (!formData.id) {
          throw new Error('Invoice ID required for update');
        }
        response = await updateInvoice(
          formData.id && formData.id.toString().trim() ? parseInt(formData.id.toString(), 10) : 0,
          submitData as UpdateInvoiceRequest
        );
      }

      if (response) {
        // Store the invoice ID for follow-up operations (like finalization)
        if (response.id) {
          setFormDataState(prev => ({ ...prev, id: response.id.toString() }));
        }
        
        // Don't show toast here - let the calling component handle success message
        // This prevents duplicate toasts
        onSuccess?.(response); // Pass response to onSuccess callback
        return true;
      } else {
        throw new Error(`Failed to ${mode} invoice`);
      }
    } catch (error) {
      console.error(`Error ${mode === 'create' ? 'creating' : 'updating'} invoice:`, error);
      
      // Report invoice form submission errors with financial tagging
      const errorToReport = error instanceof Error ? error : new Error(String(error));
      reportError(errorToReport, {
        component: 'useInvoiceForm',
        action: mode === 'create' ? 'create_invoice' : 'update_invoice',
        tags: {
          financial: true,
        },
        extra: {
          invoice: {
            mode,
            propertyId: formData.property_id,
            recipientType,
            lineItemsCount: lineItems.length,
            taxesCount: formData.taxes?.length || 0,
          }
        },
      }, 'error');
      
      toast.error(error instanceof Error ? error.message : `Failed to ${mode} invoice`);
      return false;
    } finally {
      setIsSubmitting(false);
    }
  }, [formData, lineItems, recipientType, calculatedTotals, validateForm, mode, onSuccess]);

  const clearUserTaxDefaultFromForm = useCallback(async () => {
    try {
      await clearUserTaxDefault();
      // Clear the tax from the form and reset the user default flag
      setFormDataState(prev => ({
        ...prev,
        taxes: [{ tax_name: "", tax_rate: "" }],
      }));
      setIsUserDefaultTax(false);
      toast.success('Tax default removed');
    } catch (error) {
      console.error('Error clearing user tax default:', error);
      
      // Report tax default clearing errors with financial context
      reportWarning(error instanceof Error ? error : new Error(String(error)), {
        component: 'useInvoiceForm',
        action: 'clear_tax_default',
        tags: {
          financial: true,
        },
      });
      
      toast.error('Failed to clear tax default');
    }
  }, []);

  const resetForm = useCallback(() => {
    setFormDataState(createInitialFormData());
    setLineItems([{
      description: '',
      quantity: '1',
      unit_price: '0.00',
      line_total: '0.00',
      is_taxable: true,
      expense_category: '',
      sort_order: 0,
    }]);
    setRecipientType(null);
    setErrors({});
    setIsUserDefaultTax(false);
  }, []);

  return {
    // State
    formData,
    lineItems,
    recipientType,
    errors,
    isSubmitting,
    calculatedTotals,
    isUserDefaultTax,
    userFavoriteTaxes,

    // Actions
    updateField,
    updateTaxes,
    addTaxLine,
    removeTaxLine,
    updateTaxLine,
    addLineItem,
    removeLineItem,
    updateLineItem,
    setRecipientType,
    setLineItems,
    validateForm,
    submitForm,
    resetForm,
    setFormData,
    clearUserTaxDefaultFromForm,
    setIsUserDefaultTax,
    setUserFavoriteTaxes,
    loadUserTaxDefault, // Export this so it can be called after starring a tax
  };
};
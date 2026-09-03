import { AnimatePresence, motion } from "framer-motion";
import React, { useState, useEffect, useCallback } from "react";
import { toast } from "react-toastify";
import { useQuery } from "@tanstack/react-query";
import { UserPlus, Building, Users } from "lucide-react";
import { createTenant } from "../../utils/api/tenants";
import { createTenantInvitation } from "../../utils/api/tenantInvitations";
import { getSeatAvailability } from "../../utils/api/tenantPortalSeats";
import { TenantStatus, TenantType } from "../../types/tenant";
import {
  TenantModalProps,
  TenantFormData,
  FieldErrors,
  TouchedFields,
  STATUS_MAPPING,
  ValidatableFieldName,
  FormChangeEvent,
  FormSubmitEvent,
  InputBlurEvent,
  isApiErrorResponse,
  isValidationErrorArray,
} from "./TenantModal.types";

/**
 * TenantModal Component
 * 
 * A fully typed modal for creating new tenant profiles (Individual or Company).
 * Features:
 * - Dynamic form fields based on tenant type
 * - Comprehensive validation with field-level error display
 * - Proper error handling for API responses
 * - Framer Motion animations
 * - Dark mode support
 * 
 * @component
 */
const TenantModal: React.FC<TenantModalProps> = ({
  isOpen,
  onClose,
  onSave,
  source,
  tenant = {},
  propertyId = null,
  unitId = null,
  unitName = "",
}) => {
  // Form state with proper typing
  const [formData, setFormData] = useState<TenantFormData>({
    tenant_type: TenantType.INDIVIDUAL,
    first_name: "",
    last_name: "",
    company_name: "",
    contact_person: "",
    phone: "",
    email: "",
    status: TenantStatus.ACTIVE,
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [touched, setTouched] = useState<TouchedFields>({});
  const [sendPortalInvitation, setSendPortalInvitation] = useState<boolean>(false);

  // Fetch seat availability
  const { data: seatAvailability, isLoading: loadingSeats } = useQuery({
    queryKey: ["tenantPortalSeats", "availability"],
    queryFn: getSeatAvailability,
    enabled: isOpen,
    refetchOnWindowFocus: false,
  });

  /**
   * Populate form when tenant data is provided or modal opens
   */
  useEffect(() => {
    if (isOpen) {
      let firstName = tenant?.first_name || "";
      let lastName = tenant?.last_name || "";

      // Parse full_name if individual name fields are not provided
      if (tenant?.full_name && (!firstName || !lastName)) {
        const nameParts = tenant.full_name.split(" ");
        firstName = nameParts[0] || "";
        lastName = nameParts.slice(1).join(" ") || "";
      }

      setFormData({
        tenant_type: (tenant?.tenant_type as TenantType) || TenantType.INDIVIDUAL,
        first_name: firstName,
        last_name: lastName,
        company_name: tenant?.company_name || "",
        contact_person: tenant?.contact_person || "",
        phone: tenant?.phone || "",
        email: tenant?.email || "",
        status: (tenant?.status as TenantStatus) || TenantStatus.ACTIVE,
      });

      // Reset error states
      setFieldErrors({});
      setError(null);
      setTouched({});
    }
  }, [
    isOpen,
    tenant?.id,
    tenant?.first_name,
    tenant?.last_name,
    tenant?.full_name,
    tenant?.tenant_type,
    tenant?.company_name,
    tenant?.contact_person,
    tenant?.phone,
    tenant?.email,
    tenant?.status,
  ]);

  /**
   * Validates a single form field based on current tenant type and field rules
   */
  const validateField = useCallback((name: ValidatableFieldName, value: string): string | null => {
    const tenantType = formData.tenant_type;

    switch (name) {
      case "first_name":
        if (tenantType === TenantType.INDIVIDUAL && (!value || value.trim() === "")) {
          return "First name is required for individual tenants";
        }
        break;

      case "last_name":
        if (tenantType === TenantType.INDIVIDUAL && (!value || value.trim() === "")) {
          return "Last name is required for individual tenants";
        }
        break;

      case "company_name":
        if (tenantType === TenantType.COMPANY && (!value || value.trim() === "")) {
          return "Company name is required for company tenants";
        }
        break;

      case "email":
        if (!value || value.trim() === "") {
          return "Email is required";
        }
        const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
        if (!emailRegex.test(value.trim())) {
          return "Please enter a valid email address";
        }
        break;

      case "phone":
        if (value && value.trim() !== "") {
          const digitsOnly = value.replace(/[^0-9]/g, "");
          if (digitsOnly.length < 10 || digitsOnly.length > 15) {
            return "Phone number must contain 10-15 digits";
          }
        }
        break;

      default:
        break;
    }

    return null;
  }, [formData.tenant_type]);

  /**
   * Handle input blur event - triggers validation for the field
   */
  const handleBlur = useCallback((e: InputBlurEvent): void => {
    const { name, value } = e.target;
    const fieldName = name as ValidatableFieldName;

    setTouched((prev) => ({
      ...prev,
      [fieldName]: true,
    }));

    const errorMessage = validateField(fieldName, value);
    if (errorMessage) {
      setFieldErrors((prev) => ({ ...prev, [fieldName]: errorMessage }));
    } else {
      setFieldErrors((prev) => {
        const updated = { ...prev };
        delete updated[fieldName];
        return updated;
      });
    }
  }, [validateField]);

  /**
   * Handle input change event - updates form data and validates if field was touched
   */
  const handleChange = useCallback((e: FormChangeEvent): void => {
    const { name, value } = e.target;
    const fieldName = name as ValidatableFieldName;

    setFormData((prev) => ({ ...prev, [fieldName]: value }));

    // Clear error when user starts typing if field was touched
    if (touched[fieldName]) {
      const errorMessage = validateField(fieldName, value);
      if (errorMessage) {
        setFieldErrors((prev) => ({ ...prev, [fieldName]: errorMessage }));
      } else {
        setFieldErrors((prev) => {
          const updated = { ...prev };
          delete updated[fieldName];
          return updated;
        });
      }
    }

    // If tenant type changed, clear related field errors
    if (fieldName === "tenant_type") {
      setFieldErrors((prev) => {
        const updated = { ...prev };
        delete updated.first_name;
        delete updated.last_name;
        delete updated.company_name;
        return updated;
      });
    }
  }, [touched, validateField]);

  /**
   * Validates all required fields in the form
   * Returns true if valid, false otherwise
   */
  const validateForm = useCallback((): boolean => {
    let isValid = true;
    const newErrors: FieldErrors = {};

    // Validate based on tenant type
    const fieldsToValidate: ValidatableFieldName[] =
      formData.tenant_type === TenantType.INDIVIDUAL
        ? ["first_name", "last_name", "email"]
        : ["company_name", "email"];

    for (const fieldName of fieldsToValidate) {
      const errorMessage = validateField(fieldName, formData[fieldName]);
      if (errorMessage) {
        newErrors[fieldName] = errorMessage;
        isValid = false;
      }
    }

    // Validate phone if provided
    if (formData.phone) {
      const phoneError = validateField("phone", formData.phone);
      if (phoneError) {
        newErrors.phone = phoneError;
        isValid = false;
      }
    }

    setFieldErrors(newErrors);
    if (!isValid) {
      setError("Please correct the highlighted fields.");
    } else {
      setError(null);
    }

    return isValid;
  }, [formData, validateField]);

  /**
   * Handle form submission
   */
  const handleSubmit = useCallback(async (e: FormSubmitEvent): Promise<void> => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    try {
      // Build tenant object with only relevant fields based on tenant type
      const tenantToCreate: Partial<Record<string, string | null>> = {
        tenant_type: formData.tenant_type,
        email: formData.email.trim(),
        status: STATUS_MAPPING[formData.status.toLowerCase()] || formData.status,
        phone: formData.phone?.trim() || null,
      };

      if (formData.tenant_type === TenantType.INDIVIDUAL) {
        // For individual tenants, only include first_name and last_name
        tenantToCreate.first_name = formData.first_name.trim();
        tenantToCreate.last_name = formData.last_name.trim();
      } else {
        // For company tenants, only include company_name and optionally contact_person
        tenantToCreate.company_name = formData.company_name.trim();
        tenantToCreate.contact_person = formData.contact_person?.trim() || null;
      }

      const response = await createTenant(tenantToCreate);

      // Send portal invitation if requested and seats are available
      if (sendPortalInvitation && response.id) {
        try {
          await createTenantInvitation(response.id);
          toast.success(`Tenant created and portal invitation sent!`);
        } catch (inviteError) {
          console.error("Failed to send portal invitation:", inviteError);
          // Still show success for tenant creation, but note invitation failed
          const tenantName =
            formData.tenant_type === TenantType.INDIVIDUAL
              ? `${formData.first_name} ${formData.last_name}`
              : formData.company_name;
          toast.success(`Tenant "${tenantName}" created successfully`);
          toast.warning("Failed to send portal invitation. You can resend it later.");
        }
      } else {
        // Show standard success toast
        const tenantName =
          formData.tenant_type === TenantType.INDIVIDUAL
            ? `${formData.first_name} ${formData.last_name}`
            : formData.company_name;
        toast.success(`Tenant "${tenantName}" created successfully`);
      }

      if (onSave) {
        const tenantResponse = {
          ...response,
          // Preserve any context data for the calling component
          unit: unitName || "",
          unit_id: unitId || null,
          current_property_id: propertyId || undefined,
        };
        onSave(tenantResponse);
      }

      // Only close if not from importLeaseModal
      if (!source || source !== "importLeaseModal") {
        onClose();
      }
    } catch (err: unknown) {
      console.error("Failed to create tenant:", err);
      let errorMessage = "Failed to create tenant. Please try again.";

      if (isApiErrorResponse(err)) {
        // Handle 409 Conflict (duplicate email)
        if (err.status === 409) {
          errorMessage = err.data?.detail as string || "A tenant with this email already exists.";
          setFieldErrors((prev) => ({
            ...prev,
            email: "This email is already in use.",
          }));
          setTouched((prev) => ({ ...prev, email: true }));
        }
        // Handle validation errors from Pydantic
        else if (err.data?.detail && isValidationErrorArray(err.data.detail)) {
          const validationErrors: FieldErrors = {};
          const generalErrors: string[] = [];

          err.data.detail.forEach((errorItem) => {
            if (errorItem.loc && errorItem.loc.length > 1) {
              const fieldName = errorItem.loc[errorItem.loc.length - 1] as ValidatableFieldName;
              validationErrors[fieldName] = errorItem.msg;
            } else {
              generalErrors.push(errorItem.msg || String(errorItem));
            }
          });

          if (Object.keys(validationErrors).length > 0) {
            setFieldErrors((prev) => ({ ...prev, ...validationErrors }));
            errorMessage = "Please correct the validation errors below.";
          }

          if (generalErrors.length > 0) {
            errorMessage = generalErrors.join(". ");
          }
        }
        // Handle other error messages
        else if (err.message) {
          errorMessage = err.message;
        }
      }

      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [validateForm, formData, onSave, onClose, source, unitName, unitId, propertyId]);

  /**
   * Helper to determine input class names based on error state
   */
  const getInputClassName = useCallback((fieldName: ValidatableFieldName): string => {
    const hasError = fieldErrors[fieldName] && touched[fieldName];
    return `w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm ${
      hasError ? 'border-red-300 dark:border-red-600' : 'border-gray-200 dark:border-gray-600'
    }`;
  }, [fieldErrors, touched]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black bg-opacity-50 backdrop-blur-sm z-[9999] flex items-center justify-center p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ type: "spring", damping: 25, stiffness: 400 }}
            className="relative w-full max-w-4xl bg-white dark:bg-gray-800 rounded-xl shadow-xl max-h-[90vh] overflow-hidden flex flex-col z-[10000]"
            onClick={(e: React.MouseEvent<HTMLDivElement>) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-50 dark:bg-blue-900/30 rounded-lg flex items-center justify-center flex-shrink-0">
                  <UserPlus className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div className="flex-1">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Add New Tenant</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Complete tenant profile
                  </p>
                </div>
                <button
                  onClick={onClose}
                  type="button"
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 p-1.5 rounded-lg transition-all"
                  aria-label="Close modal"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Content */}
            <form id="tenant-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900">
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mx-4 mt-3 p-2.5 bg-red-50 dark:bg-red-900/50 border border-red-100 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg"
                  role="alert"
                >
                  <div className="flex">
                    <svg className="h-5 w-5 text-red-400 mr-2 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                    <span className="text-sm">{error}</span>
                  </div>
                </motion.div>
              )}

              <div className="p-4 space-y-2.5">
                {/* Portal Invitation Section - MOVED TO TOP */}
                <div className="bg-gradient-to-br from-indigo-50 to-blue-50 dark:from-indigo-950/30 dark:to-blue-950/30 rounded-lg p-3.5 shadow-sm border border-indigo-100 dark:border-indigo-900/50">
                  <div className="flex items-start justify-between mb-2.5">
                    <div className="flex items-center">
                      <div className="w-7 h-7 bg-indigo-100 dark:bg-indigo-900/50 rounded-lg flex items-center justify-center mr-2">
                        <Users className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Tenant Portal Access</h3>
                        <p className="text-xs text-gray-600 dark:text-gray-400">Empower tenants with self-service tools</p>
                      </div>
                    </div>
                  </div>

                  {/* Benefits - Compact 2-column grid */}
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 mb-2.5">
                    <div className="flex items-start text-xs text-gray-700 dark:text-gray-300">
                      <svg className="w-3 h-3 text-indigo-500 dark:text-indigo-400 mr-1.5 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span><strong className="font-semibold">Pay rent online</strong> via Stripe</span>
                    </div>
                    <div className="flex items-start text-xs text-gray-700 dark:text-gray-300">
                      <svg className="w-3 h-3 text-indigo-500 dark:text-indigo-400 mr-1.5 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span><strong className="font-semibold">Submit requests</strong> with tracking</span>
                    </div>
                    <div className="flex items-start text-xs text-gray-700 dark:text-gray-300">
                      <svg className="w-3 h-3 text-indigo-500 dark:text-indigo-400 mr-1.5 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span><strong className="font-semibold">Access documents</strong> & leases</span>
                    </div>
                    <div className="flex items-start text-xs text-gray-700 dark:text-gray-300">
                      <svg className="w-3 h-3 text-indigo-500 dark:text-indigo-400 mr-1.5 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span><strong className="font-semibold">Real-time notifications</strong></span>
                    </div>
                  </div>

                  {loadingSeats ? (
                    <div className="flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 py-2">
                      <div className="w-4 h-4 border-2 border-gray-300 border-t-indigo-600 rounded-full animate-spin mr-2" />
                      Checking availability...
                    </div>
                  ) : seatAvailability && seatAvailability.available > 0 ? (
                    <div className="space-y-2">
                      {/* Card-based Selection */}
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setSendPortalInvitation(true)}
                          disabled={!formData.email || !formData.email.trim()}
                          className={`relative text-left p-2.5 rounded-lg border-2 transition-all ${
                            sendPortalInvitation
                              ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/50'
                              : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 hover:border-indigo-300 dark:hover:border-indigo-700'
                          } ${(!formData.email || !formData.email.trim()) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                        >
                          {sendPortalInvitation && (
                            <div className="absolute top-2 right-2">
                              <svg className="w-4 h-4 text-indigo-600 dark:text-indigo-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                              </svg>
                            </div>
                          )}
                          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-0.5">✉️ Send Invitation</div>
                          <div className="text-xs text-gray-600 dark:text-gray-400">
                            {!formData.email || !formData.email.trim() ? 'Requires email' : 'Invite after creation'}
                          </div>
                        </button>
                        
                        <button
                          type="button"
                          onClick={() => setSendPortalInvitation(false)}
                          className={`relative text-left p-2.5 rounded-lg border-2 transition-all cursor-pointer ${
                            !sendPortalInvitation
                              ? 'border-gray-400 dark:border-gray-600 bg-gray-50 dark:bg-gray-800'
                              : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 hover:border-gray-300 dark:hover:border-gray-600'
                          }`}
                        >
                          {!sendPortalInvitation && (
                            <div className="absolute top-2 right-2">
                              <svg className="w-4 h-4 text-gray-600 dark:text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                              </svg>
                            </div>
                          )}
                          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-0.5">⏭️ Skip for Now</div>
                          <div className="text-xs text-gray-600 dark:text-gray-400">Invite later</div>
                        </button>
                      </div>

                      <div className="flex items-center text-xs text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-gray-800/30 rounded-lg px-2.5 py-1.5 border border-indigo-100 dark:border-indigo-900">
                        <svg className="w-3 h-3 text-green-500 dark:text-green-400 mr-1.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        <span>
                          <strong className="text-gray-900 dark:text-gray-100">{seatAvailability.available}</strong> seat{seatAvailability.available !== 1 ? 's' : ''} available
                          {seatAvailability.free_seats > 0 && (
                            <span className="text-gray-500 dark:text-gray-400"> • {seatAvailability.free_seats} free</span>
                          )}
                        </span>
                      </div>
                    </div>
                  ) : seatAvailability && seatAvailability.available === 0 ? (
                    <div className="bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 border-2 border-amber-200 dark:border-amber-800 rounded-lg p-2.5">
                      <div className="flex items-start mb-2">
                        <svg className="w-4 h-4 text-amber-500 dark:text-amber-400 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                        </svg>
                        <div className="flex-1">
                          <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">All {seatAvailability.limit} seats in use</p>
                          <p className="text-xs text-amber-800 dark:text-amber-300 mt-0.5">
                            Add more seats to invite this tenant to the portal
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => window.open('/tenants', '_blank')}
                        className="w-full bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white text-xs font-semibold py-1.5 px-3 rounded-lg transition-all shadow-sm flex items-center justify-center gap-1.5"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                        </svg>
                        Add Seats ($3/month each)
                      </button>
                    </div>
                  ) : null}
                </div>

                {/* Tenant Type Section */}
                <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm border border-gray-100 dark:border-gray-700">
                  <div className="flex items-center mb-2">
                    <div className="w-7 h-7 bg-purple-50 dark:bg-purple-900/30 rounded-lg flex items-center justify-center mr-2">
                      <Building className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                    </div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Tenant Type</h3>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <label className="flex items-center cursor-pointer">
                      <input
                        type="radio"
                        name="tenant_type"
                        value={TenantType.INDIVIDUAL}
                        checked={formData.tenant_type === TenantType.INDIVIDUAL}
                        onChange={handleChange}
                        className="mr-3 text-blue-600 dark:text-blue-500 focus:ring-blue-500"
                      />
                      <div className="flex items-center">
                        <svg className="w-5 h-5 text-gray-400 dark:text-gray-500 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Individual</span>
                      </div>
                    </label>
                    <label className="flex items-center cursor-pointer">
                      <input
                        type="radio"
                        name="tenant_type"
                        value={TenantType.COMPANY}
                        checked={formData.tenant_type === TenantType.COMPANY}
                        onChange={handleChange}
                        className="mr-3 text-blue-600 dark:text-blue-500 focus:ring-blue-500"
                      />
                      <div className="flex items-center">
                        <svg className="w-5 h-5 text-gray-400 dark:text-gray-500 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                        </svg>
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Company</span>
                      </div>
                    </label>
                  </div>
                </div>

                {/* Tenant Information Section - Combined Personal/Company + Contact */}
                <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm border border-gray-100 dark:border-gray-700">
                  <div className="flex items-center mb-2">
                    <div className="w-7 h-7 bg-blue-50 dark:bg-blue-900/30 rounded-lg flex items-center justify-center mr-2">
                      <UserPlus className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    </div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Tenant Information</h3>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    {formData.tenant_type === TenantType.INDIVIDUAL ? (
                      <>
                        <div>
                          <label htmlFor="first_name" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            First Name <span className="text-red-500 dark:text-red-400">*</span>
                          </label>
                          <input
                            id="first_name"
                            name="first_name"
                            type="text"
                            value={formData.first_name}
                            onChange={handleChange}
                            onBlur={handleBlur}
                            placeholder="Enter first name"
                            className={getInputClassName("first_name")}
                            required
                            aria-required="true"
                            aria-invalid={!!(fieldErrors.first_name && touched.first_name)}
                            aria-describedby={fieldErrors.first_name && touched.first_name ? "first_name-error" : undefined}
                          />
                          {fieldErrors.first_name && touched.first_name && (
                            <p id="first_name-error" className="mt-1 text-xs text-red-600 dark:text-red-400" role="alert">
                              {fieldErrors.first_name}
                            </p>
                          )}
                        </div>

                        <div>
                          <label htmlFor="last_name" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Last Name <span className="text-red-500 dark:text-red-400">*</span>
                          </label>
                          <input
                            id="last_name"
                            name="last_name"
                            type="text"
                            value={formData.last_name}
                            onChange={handleChange}
                            onBlur={handleBlur}
                            placeholder="Enter last name"
                            className={getInputClassName("last_name")}
                            required
                            aria-required="true"
                            aria-invalid={!!(fieldErrors.last_name && touched.last_name)}
                            aria-describedby={fieldErrors.last_name && touched.last_name ? "last_name-error" : undefined}
                          />
                          {fieldErrors.last_name && touched.last_name && (
                            <p id="last_name-error" className="mt-1 text-xs text-red-600 dark:text-red-400" role="alert">
                              {fieldErrors.last_name}
                            </p>
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        <div>
                          <label htmlFor="company_name" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Company Name <span className="text-red-500 dark:text-red-400">*</span>
                          </label>
                          <input
                            id="company_name"
                            name="company_name"
                            type="text"
                            value={formData.company_name}
                            onChange={handleChange}
                            onBlur={handleBlur}
                            placeholder="Enter company name"
                            className={getInputClassName("company_name")}
                            required
                            aria-required="true"
                            aria-invalid={!!(fieldErrors.company_name && touched.company_name)}
                            aria-describedby={fieldErrors.company_name && touched.company_name ? "company_name-error" : undefined}
                          />
                          {fieldErrors.company_name && touched.company_name && (
                            <p id="company_name-error" className="mt-1 text-xs text-red-600 dark:text-red-400" role="alert">
                              {fieldErrors.company_name}
                            </p>
                          )}
                        </div>

                        <div>
                          <label htmlFor="contact_person" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Contact Person
                          </label>
                          <input
                            id="contact_person"
                            name="contact_person"
                            type="text"
                            value={formData.contact_person}
                            onChange={handleChange}
                            onBlur={handleBlur}
                            placeholder="Enter contact person name"
                            className="w-full px-3 py-2 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                          />
                        </div>
                      </>
                    )}

                    <div>
                      <label htmlFor="email" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        Email <span className="text-red-500 dark:text-red-400">*</span>
                      </label>
                      <input
                        id="email"
                        name="email"
                        type="email"
                        value={formData.email}
                        onChange={handleChange}
                        onBlur={handleBlur}
                        placeholder="Enter email address"
                        className={getInputClassName("email")}
                        required
                        aria-required="true"
                        aria-invalid={!!(fieldErrors.email && touched.email)}
                        aria-describedby={fieldErrors.email && touched.email ? "email-error" : undefined}
                      />
                      {fieldErrors.email && touched.email && (
                        <p id="email-error" className="mt-1 text-xs text-red-600 dark:text-red-400" role="alert">
                          {fieldErrors.email}
                        </p>
                      )}
                    </div>

                    <div>
                      <label htmlFor="phone" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        Phone Number
                      </label>
                      <input
                        id="phone"
                        name="phone"
                        type="tel"
                        value={formData.phone}
                        onChange={handleChange}
                        onBlur={handleBlur}
                        placeholder="Enter phone number"
                        className={getInputClassName("phone")}
                        aria-invalid={!!(fieldErrors.phone && touched.phone)}
                        aria-describedby={fieldErrors.phone && touched.phone ? "phone-error" : undefined}
                      />
                      {fieldErrors.phone && touched.phone && (
                        <p id="phone-error" className="mt-1 text-xs text-red-600 dark:text-red-400" role="alert">
                          {fieldErrors.phone}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </form>

            {/* Footer */}
            <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="text-xs text-gray-500 dark:text-gray-400 flex items-start">
                  <svg className="w-3.5 h-3.5 mr-1.5 text-gray-400 dark:text-gray-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>
                    <span className="text-red-600 dark:text-red-400 font-bold">*</span> Required fields
                  </span>
                </div>
                <div className="flex gap-3 flex-shrink-0">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 transition-all text-sm font-medium"
                    disabled={isLoading}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    form="tenant-form"
                    className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all text-sm font-medium flex items-center gap-2 min-w-[140px] justify-center shadow-sm"
                    disabled={isLoading}
                  >
                    {isLoading ? (
                      <>
                        <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Creating...
                      </>
                    ) : (
                      'Save Tenant'
                    )}
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default TenantModal;

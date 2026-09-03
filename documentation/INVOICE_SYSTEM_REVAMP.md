# Invoice System - Current State

## ✅ Complete & Working

- **Line items:** Add/edit/delete with description, quantity, price, taxable flag, expense category
- **Multi-tax:** Multiple taxes per invoice, calculated only on taxable items
- **Drafts:** LocalStorage auto-save (10s) + database drafts + restore prompt
- **Recipients:** Tenant/Vendor/OwnershipEntity with snapshot capture
- **Delivery methods:** Save Locally / Send Invoice / Request Payment (UI + backend wired)
- **Real-time calculations:** Subtotal, tax breakdown, grand total
- **User tax preferences:** Save/load favorite taxes with star button

## ✅ PDF Generation & Delivery - COMPLETE

**Status:** ✅ Full PDF support with Azure Blob Storage

**Implementation:**

- `Backend/api/accounting/invoices/pdf_service.py` - PDF generation + blob upload
- `Backend/api/notifications/sendgrid_service.py` - Email with PDF attachment support
- `Backend/api/accounting/invoices/service.py` - Integrated into delivery flow
- `Backend/api/accounting/invoices/router.py` - PDF download endpoint (serves from blob)
- `Backend/utils/azure_blob.py` - `upload_invoice_pdf_to_blob()` function
- `Backend/models/accounting/invoice.py` - Added `pdf_blob_url` and `pdf_generated_at`

**Features:**

- ✅ Professional branded PDFs matching frontend preview
- ✅ SEND_INVOICE: Email with PDF attachment → stored in blob
- ✅ REQUEST_PAYMENT: Stripe invoice + branded email with PDF → stored in blob
- ✅ SAVE_LOCALLY: PDF stored in blob → download via API endpoint
- ✅ Azure Blob Storage: Permanent PDF storage for audit trail
- ✅ Performance: Serve from blob (instant) instead of regenerating
- ✅ Optimized generation: 200-800ms, ~50-200KB file size

**Database Schema:**

- `invoices.pdf_blob_url` - Azure Blob Storage URL for PDF
- `invoices.pdf_generated_at` - Timestamp when PDF was generated

## 📋 TODO (Priority Order)

1. ~~**PDF Generation & Delivery**~~ ✅ COMPLETE
2. ~~**Azure Blob Storage for PDFs**~~ ✅ COMPLETE
3. ~~**Frontend: Instant invoice updates + PDF download**~~ ✅ COMPLETE
   - React Query cache invalidation for instant table updates
   - PDF download button in actions column
4. **Run migration: `20260121000000_add_invoice_pdf_blob_storage.sql`**
5. **Stripe Connect UI**
   - InvoicesTab: Connection status banner
   - Integrations page: StripeConnectCard
   - Disable "Request Payment" if not connected
6. **Invoice Preview Polish**
   - Match React preview exactly in PDF template
   - Brikli logo, colors, proper formatting
7. **Minor Fixes**
   - RecipientSelector: "All Properties" → "None"
   - Remove console.log debug statements

## 🔑 Key Files

**Backend:**

- `api/accounting/invoices/service.py` - Invoice CRUD, delivery handler
- `api/accounting/invoices/pdf_service.py` - PDF generation (WeasyPrint)
- `api/accounting/invoices/invoice_template.py` - HTML template generator
- `api/accounting/invoices/router.py` - API endpoints including PDF download
- `api/accounting/invoices/helpers.py` - Tax/line item calculations
- `api/accounting/invoices/recipients.py` - Recipient snapshot logic
- `api/notifications/sendgrid_service.py` - Email with attachment support
- `models/accounting/invoice*.py` - ORM models

**Frontend:**

- `pages/InvoiceCreatePage.tsx` - Full-page invoice creation with React Query cache invalidation
- `components/accounting/InvoicesTab.tsx` - Invoice list with PDF download buttons
- `hooks/accounting/useInvoiceForm.ts` - Form state (passes deliveryMethod)
- `components/accounting/InvoicePreview.tsx` - Preview component
- `types/accounting.ts` - TypeScript types including pdf_blob_url

**Delivery Flow:**

```
Frontend (deliveryMethod, is_draft: false) → useInvoiceForm → API → 
Backend creates finalized invoice → _handle_invoice_delivery() →
  SEND_INVOICE: ✅ Generate PDF → Upload to Azure Blob → Email with PDF
  REQUEST_PAYMENT: ✅ Stripe invoice → Generate PDF → Upload to blob → Email
  SAVE_LOCALLY: ✅ Generate PDF → Upload to Azure Blob → Ready for download

Invoice is created with status=Pending, is_draft=false
All delivery methods create finalized invoices immediately (no draft step)

Download Flow:
Frontend calls GET /api/invoices/{id}/pdf →
  If pdf_blob_url exists: Redirect to Azure Blob (instant) ⚡
  Else: Generate on-the-fly (fallback)
```

## 🐛 Recent Fixes

- ✅ deliveryMethod prop threading (frontend → backend)
- ✅ Stripe API params (customer vs customer_email)
- ✅ Type safety (Invoice type, no `any`)
- ✅ Variable declaration order (deliveryMethod before useInvoiceForm)
- ✅ Navigation target (/accounting/invoices not /accounting)
- ✅ Duplicate toast prevention
- ✅ Import errors (get_connected_account_for_landlord)
- ✅ React Query cache invalidation for instant table updates
- ✅ Create invoices as finalized (is_draft: false) instead of draft + finalize
- ✅ Backend respects is_draft from frontend and auto-triggers delivery on create
- ✅ PDF authentication error - implemented secure URL with SAS tokens
- ✅ PDF corners cutoff - removed border-radius for clean edges
- ✅ PDF sender info - dynamically uses landlord info instead of hardcoded Brikli

## 📦 Database Schema

**Tables:**

- `invoice_line_items` - Line items with qty, price, taxable flag
- `invoice_tax_details` - Tax name, rate, amount per invoice
- `invoices` - Enhanced with recipient fields, audit trail, delivery_method

**Key Columns:**

- `invoices.is_draft` - Draft vs finalized
- `invoices.delivery_method` - save_locally / send_invoice / request_payment
- `invoices.recipient_type` - tenant / ownership_entity / vendor
- `invoices.recipient_*` - Snapshot fields (name, email, address, etc.)

**Migrations Applied:**

- `20260115003059_add_invoice_line_items_and_taxes.sql`
- `20260115062224_add_stripe_customer_ids_and_invoice_fields.sql`
- `20260121000000_add_invoice_pdf_blob_storage.sql` ⏳ TO RUN

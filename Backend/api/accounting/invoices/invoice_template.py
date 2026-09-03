"""
Professional Invoice Template System for Brikli

Generates branded HTML invoices that match Brikli's email template design.
Invoices are production-ready for:
- Email delivery
- PDF generation  
- Web viewing
- Embedded Stripe payment collection
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
import html

from Backend.models.accounting.invoice import Invoice
from Backend.models.accounting.invoice_line_item import InvoiceLineItem
from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetail


class BrikliInvoiceTemplate:
    """Professional invoice HTML generator with Brikli branding"""
    
    BRIKLI_GREEN = "#004225"
    BRIKLI_GREEN_HOVER = "#016231"
    LOGO_URL = "https://app.brikli.com/BrikliTransparentWhite.png"
    
    @staticmethod
    def generate_invoice_html(
        invoice: Invoice,
        line_items: List[InvoiceLineItem],
        taxes: List[InvoiceTaxDetail],
        company_info: Optional[dict] = None,
        stripe_payment_url: Optional[str] = None
    ) -> str:
        """
        Generate complete HTML invoice.
        
        Args:
            invoice: Invoice ORM object
            line_items: List of line items
            taxes: List of tax details
            company_info: Optional company information override
            stripe_payment_url: Optional Stripe payment link
            
        Returns:
            Complete HTML invoice string
        """
        
        # Default company info
        if not company_info:
            company_info = {
                'name': 'Brikli Property Management',
                'address': '5671 Avenue Midway',
                'address_2': 'Cote Saint Luc Quebec H4W1K7',
                'country': 'Canada',
                'email': 'billing@brikli.com',
                'phone': '+1 (514) 555-0100'
            }
        
        # Calculate totals with taxable/non-taxable breakdown
        from .calculations import calculate_subtotal_breakdown
        taxable_subtotal, non_taxable_subtotal, subtotal = calculate_subtotal_breakdown(line_items)
        total_tax = sum(tax.tax_amount for tax in taxes)
        grand_total = invoice.amount
        
        # Determine if we need to show breakdown (if both taxable and non-taxable items exist)
        show_breakdown = taxable_subtotal > 0 and non_taxable_subtotal > 0
        
        # Format dates
        issue_date = invoice.issue_date.strftime("%B %d, %Y")
        due_date = invoice.due_date.strftime("%B %d, %Y")
        
        # Build line items HTML
        line_items_html = BrikliInvoiceTemplate._build_line_items_table(line_items)
        
        # Build enhanced totals section with breakdown
        totals_html = BrikliInvoiceTemplate._build_totals_section(
            subtotal=subtotal,
            taxable_subtotal=taxable_subtotal,
            non_taxable_subtotal=non_taxable_subtotal,
            show_breakdown=show_breakdown,
            taxes=taxes,
            grand_total=grand_total
        )
        
        # Build recipient info
        recipient_html = BrikliInvoiceTemplate._build_recipient_info(invoice)
        
        # Build tax context section (property/jurisdiction info)
        tax_context_html = BrikliInvoiceTemplate._build_tax_context_section(invoice)
        
        # Build payment section
        payment_html = BrikliInvoiceTemplate._build_payment_section(
            invoice, stripe_payment_url, grand_total
        )
        
        # Escape all user-provided content
        safe_invoice_number = html.escape(invoice.invoice_number)
        safe_company_name = html.escape(company_info['name'])
        safe_company_address = html.escape(company_info['address'])
        safe_company_address_2 = html.escape(company_info['address_2'])
        safe_company_country = html.escape(company_info['country'])
        safe_company_email = html.escape(company_info['email'])
        safe_company_phone = html.escape(company_info['phone'])
        
        # Complete HTML
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Invoice {safe_invoice_number}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #f9fafb;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #111827;
      line-height: 1.6;
    }}
    .invoice-container {{
      max-width: 800px;
      margin: 40px auto;
      background-color: #ffffff;
      border-radius: 0;
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
      overflow: hidden;
    }}
    .invoice-header {{
      background-color: {BrikliInvoiceTemplate.BRIKLI_GREEN};
      padding: 48px 48px 32px 48px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }}
    .invoice-header img {{
      width: 150px;
      height: auto;
      image-rendering: -webkit-optimize-contrast;
      image-rendering: crisp-edges;
    }}
    .invoice-number {{
      text-align: right;
      color: #ffffff;
    }}
    .invoice-number h1 {{
      margin: 0;
      font-size: 28px;
      font-weight: 700;
    }}
    .invoice-number p {{
      margin: 8px 0 0 0;
      font-size: 14px;
      opacity: 0.9;
    }}
    .invoice-content {{
      padding: 40px 48px;
    }}
    .info-section {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 32px;
      margin-bottom: 40px;
      padding-bottom: 32px;
      border-bottom: 2px solid #e5e7eb;
    }}
    .info-box {{
      min-width: 0;
    }}
    .info-box h3 {{
      margin: 0 0 12px 0;
      font-size: 12px;
      font-weight: 600;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .info-box p {{
      margin: 0 0 4px 0;
      font-size: 14px;
      color: #111827;
    }}
    .info-box .highlight {{
      font-weight: 600;
      color: {BrikliInvoiceTemplate.BRIKLI_GREEN};
    }}
    .line-items {{
      margin: 32px 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    thead {{
      background-color: #f9fafb;
    }}
    th {{
      text-align: left;
      padding: 12px 16px;
      font-size: 12px;
      font-weight: 600;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 2px solid #e5e7eb;
    }}
    th.align-right {{
      text-align: right;
    }}
    td {{
      padding: 16px;
      border-bottom: 1px solid #f3f4f6;
      font-size: 14px;
    }}
    td.align-right {{
      text-align: right;
    }}
    tbody tr:hover {{
      background-color: #f9fafb;
    }}
    .line-desc {{
      font-weight: 500;
      color: #111827;
      margin-bottom: 4px;
    }}
    .line-meta {{
      font-size: 12px;
      color: #6b7280;
    }}
    .totals-section {{
      margin-top: 32px;
      padding: 24px 0 0 0;
      border-top: 2px solid #e5e7eb;
    }}
    .totals-table {{
      margin-left: auto;
      width: 380px;
    }}
    .totals-row {{
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      font-size: 15px;
      color: #374151;
    }}
    .totals-row.subtotal {{
      color: #6b7280;
      font-size: 14px;
    }}
    .totals-row.tax {{
      color: #6b7280;
      font-size: 14px;
      padding-left: 20px;
    }}
    .totals-row.total {{
      border-top: 3px solid #004225;
      padding-top: 16px;
      margin-top: 12px;
      font-size: 20px;
      font-weight: 700;
      color: {BrikliInvoiceTemplate.BRIKLI_GREEN};
    }}
    .payment-section {{
      margin-top: 40px;
      padding: 32px;
      background-color: #f9fafb;
      border-radius: 12px;
      text-align: center;
    }}
    .payment-button {{
      display: inline-block;
      background-color: {BrikliInvoiceTemplate.BRIKLI_GREEN};
      color: #ffffff !important;
      text-decoration: none;
      font-weight: 600;
      font-size: 16px;
      padding: 16px 48px;
      border-radius: 10px;
      margin: 16px 0;
      transition: background-color 0.3s ease;
    }}
    .payment-button:hover {{
      background-color: {BrikliInvoiceTemplate.BRIKLI_GREEN_HOVER};
    }}
    .status-badge {{
      display: inline-block;
      padding: 6px 16px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .status-pending {{
      background-color: #fef3c7;
      color: #92400e;
    }}
    .status-paid {{
      background-color: #d1fae5;
      color: #065f46;
    }}
    .status-overdue {{
      background-color: #fee2e2;
      color: #991b1b;
    }}
    .status-draft {{
      background-color: #e5e7eb;
      color: #374151;
    }}
    .footer {{
      border-top: 2px solid #e5e7eb;
      padding: 32px 48px;
      text-align: center;
      font-size: 13px;
      color: #6b7280;
    }}
    .footer p {{
      margin: 8px 0;
    }}
    .footer a {{
      color: {BrikliInvoiceTemplate.BRIKLI_GREEN};
      text-decoration: none;
    }}
    @media print {{
      body {{
        background-color: #ffffff;
      }}
      .invoice-container {{
        box-shadow: none;
        margin: 0;
        border-radius: 0;
      }}
      .invoice-header img {{
        image-rendering: -webkit-optimize-contrast;
        image-rendering: crisp-edges;
      }}
      .payment-section {{
        display: none;
      }}
    }}
  </style>
</head>
<body>
  <div class="invoice-container">
    <!-- Header -->
    <div class="invoice-header">
      <img src="{BrikliInvoiceTemplate.LOGO_URL}" alt="Brikli Logo" />
      <div class="invoice-number">
        <h1>INVOICE</h1>
        <p>#{safe_invoice_number}</p>
      </div>
    </div>

    <!-- Content -->
    <div class="invoice-content">
      <!-- Info Section -->
      <div class="info-section">
        <!-- From (Company) -->
        <div class="info-box">
          <h3>From</h3>
          <p class="highlight">{safe_company_name}</p>
          <p>{safe_company_address}</p>
          <p>{safe_company_address_2}</p>
          <p>{safe_company_country}</p>
          <p style="margin-top: 8px;">{safe_company_email}</p>
          <p>{safe_company_phone}</p>
        </div>

        <!-- Bill To (Recipient) -->
        <div class="info-box">
          {recipient_html}
        </div>

        <!-- Invoice Details -->
        <div class="info-box">
          <h3>Details</h3>
          <p><strong>Issue Date:</strong> {issue_date}</p>
          <p><strong>Due Date:</strong> {due_date}</p>
        </div>
      </div>

      <!-- Line Items -->
      <div class="line-items">
        <table>
          <thead>
            <tr>
              <th>Description</th>
              <th class="align-right">Qty</th>
              <th class="align-right">Unit Price</th>
              <th class="align-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {line_items_html}
          </tbody>
        </table>
      </div>

      <!-- Enhanced Totals Section -->
      {totals_html}

      {tax_context_html}

      {payment_html}
    </div>

    <!-- Footer -->
    <div class="footer">
      <p><strong>Thank you for your business!</strong></p>
      <p>Questions about this invoice? Contact <a href="mailto:{safe_company_email}">{safe_company_email}</a></p>
      <p style="margin-top: 16px;">© 2025 Brikli. All rights reserved.</p>
    </div>
  </div>
</body>
</html>"""
    
    @staticmethod
    def _build_line_items_table(line_items: List[InvoiceLineItem]) -> str:
        """Build HTML for line items table rows"""
        rows_html = ""
        
        for item in line_items:
            safe_desc = html.escape(item.description)
            safe_category = html.escape(item.expense_category or "")
            
            # Build description with metadata
            desc_html = f'<div class="line-desc">{safe_desc}</div>'
            
            meta_parts = []
            if item.expense_category:
                meta_parts.append(f'Category: {safe_category}')
            if not item.is_taxable:
                meta_parts.append('Tax Exempt')
            
            if meta_parts:
                desc_html += f'<div class="line-meta">{" • ".join(meta_parts)}</div>'
            
            rows_html += f"""
            <tr>
              <td>{desc_html}</td>
              <td class="align-right">{item.quantity}</td>
              <td class="align-right">${item.unit_price:.2f}</td>
              <td class="align-right"><strong>${item.line_total:.2f}</strong></td>
            </tr>"""
        
        return rows_html
    
    @staticmethod
    def _build_taxes_rows(taxes: List[InvoiceTaxDetail]) -> str:
        """Build HTML for tax rows (legacy - kept for backward compatibility)"""
        taxes_html = ""
        
        for tax in taxes:
            safe_tax_name = html.escape(tax.tax_name)
            taxes_html += f"""
          <div class="totals-row tax">
            <span>{safe_tax_name} ({tax.tax_rate}%)</span>
            <span>${tax.tax_amount:.2f}</span>
          </div>"""
        
        return taxes_html
    
    @staticmethod
    def _build_totals_section(
        subtotal: Decimal,
        taxable_subtotal: Decimal,
        non_taxable_subtotal: Decimal,
        show_breakdown: bool,
        taxes: List[InvoiceTaxDetail],
        grand_total: Decimal
    ) -> str:
        """
        Build enhanced totals section with taxable/non-taxable breakdown.
        
        This section provides professional accounting clarity by showing:
        - Subtotal breakdown (taxable vs non-taxable)
        - Clear tax application on taxable items only
        - Grand total
        
        Args:
            subtotal: Total subtotal
            taxable_subtotal: Subtotal of taxable items
            non_taxable_subtotal: Subtotal of non-taxable items
            show_breakdown: Whether to show detailed breakdown
            taxes: List of tax details
            grand_total: Final invoice total
        
        Returns:
            HTML string for totals section
        """
        html_parts = ['<div class="totals-section"><div class="totals-table">']
        
        # Subtotal Section
        if show_breakdown:
            # Show detailed breakdown when there are both taxable and non-taxable items
            html_parts.append(f"""
          <div class="totals-row subtotal">
            <span>Subtotal (Taxable)</span>
            <span>${taxable_subtotal:.2f}</span>
          </div>
          <div class="totals-row subtotal">
            <span>Subtotal (Non-Taxable)</span>
            <span>${non_taxable_subtotal:.2f}</span>
          </div>
          <div style="border-top: 1px solid #e5e7eb; margin: 8px 0;"></div>
          <div class="totals-row subtotal" style="font-weight: 600;">
            <span>Total Subtotal</span>
            <span>${subtotal:.2f}</span>
          </div>""")
        else:
            # Simple subtotal if all items have the same tax status
            html_parts.append(f"""
          <div class="totals-row subtotal">
            <span>Subtotal</span>
            <span>${subtotal:.2f}</span>
          </div>""")
        
        # Taxes Section
        if taxes and len(taxes) > 0:
            html_parts.append('<div style="border-top: 1px solid #e5e7eb; margin: 12px 0;"></div>')
            
            # Tax header with explanation
            tax_note = " (applied to taxable items)" if taxable_subtotal > 0 else ""
            html_parts.append(f"""
          <div style="font-size: 13px; color: #6b7280; font-weight: 600; margin-bottom: 8px;">
            Taxes{tax_note}:
          </div>""")
            
            # Individual tax lines
            for tax in taxes:
                safe_tax_name = html.escape(tax.tax_name)
                html_parts.append(f"""
          <div class="totals-row tax">
            <span>{safe_tax_name} ({tax.tax_rate}%)</span>
            <span>${tax.tax_amount:.2f}</span>
          </div>""")
        
        # Grand Total
        html_parts.append(f"""
          <div class="totals-row total">
            <span>Total Due</span>
            <span>${grand_total:.2f}</span>
          </div>
        </div>
      </div>""")
        
        return "\n".join(html_parts)
    
    @staticmethod
    def _build_tax_context_section(invoice: Invoice) -> str:
        """
        Build tax context section to explain tax jurisdiction and basis.
        
        This provides transparency about WHERE and WHY taxes were applied,
        which is critical for accounting compliance and customer trust.
        
        Args:
            invoice: Invoice ORM object (with property relationship if loaded)
        
        Returns:
            HTML string for tax context section (compact, single-line format)
        """
        # Only show if invoice has taxes
        if not invoice.taxes or len(invoice.taxes) == 0:
            return ""
        
        # Build location string from property or recipient address
        location_parts = []
        
        # Try to get property location first
        if hasattr(invoice, 'property') and invoice.property:
            property_obj = invoice.property
            if hasattr(property_obj, 'city') and property_obj.city:
                location_parts.append(html.escape(property_obj.city))
            if hasattr(property_obj, 'province') and property_obj.province:
                location_parts.append(html.escape(property_obj.province))
        
        # Fallback to recipient address
        if not location_parts:
            if invoice.recipient_city:
                location_parts.append(html.escape(invoice.recipient_city))
            if invoice.recipient_province:
                location_parts.append(html.escape(invoice.recipient_province))
        
        # Default to Canada if we have no specific location
        if not location_parts:
            location_parts = ["Canada"]
        
        location_str = ", ".join(location_parts)
        
        return f"""
      <div style="margin-top: 16px; padding: 10px 16px; background-color: #f9fafb; border-radius: 6px; border-left: 3px solid #004225;">
        <p style="margin: 0; font-size: 11px; color: #6b7280; line-height: 1.4;">
          <strong style="color: #374151;">Tax Jurisdiction:</strong> {location_str} • Taxes calculated based on property location at time of invoice issuance.
        </p>
      </div>"""
    
    @staticmethod
    def _build_recipient_info(invoice: Invoice) -> str:
        """Build HTML for recipient information"""
        if not invoice.recipient_name:
            return '<h3>Bill To</h3><p><em>No recipient specified</em></p>'
        
        safe_name = html.escape(invoice.recipient_name or "")
        safe_company = html.escape(invoice.recipient_company or "") if invoice.recipient_company else ""
        safe_email = html.escape(invoice.recipient_email or "") if invoice.recipient_email else ""
        
        html_parts = ['<h3>Bill To</h3>']
        html_parts.append(f'<p class="highlight">{safe_name}</p>')
        
        if safe_company and safe_company != safe_name:
            html_parts.append(f'<p>{safe_company}</p>')
        
        if invoice.recipient_address_line1:
            safe_addr1 = html.escape(invoice.recipient_address_line1)
            html_parts.append(f'<p>{safe_addr1}</p>')
        
        if invoice.recipient_city or invoice.recipient_province:
            city = html.escape(invoice.recipient_city or "")
            province = html.escape(invoice.recipient_province or "")
            postal = html.escape(invoice.recipient_postal_code or "")
            html_parts.append(f'<p>{city} {province} {postal}</p>')
        
        if invoice.recipient_country and invoice.recipient_country != "Canada":
            safe_country = html.escape(invoice.recipient_country)
            html_parts.append(f'<p>{safe_country}</p>')
        
        if safe_email:
            html_parts.append(f'<p style="margin-top: 8px;">{safe_email}</p>')
        
        return "\n".join(html_parts)
    
    @staticmethod
    def _build_payment_section(invoice: Invoice, stripe_url: Optional[str], amount: Decimal) -> str:
        """Build HTML for payment section"""
        
        status_value = invoice.status.value if hasattr(invoice.status, 'value') else invoice.status
        if status_value in ['Paid', 'Refunded']:
            return """
      <div class="payment-section">
        <p style="color: #065f46; font-weight: 600;">✓ This invoice has been paid</p>
      </div>"""
        
        if not stripe_url:
            return """
      <div class="payment-section">
        <p style="color: #6b7280;">Payment instructions will be provided separately.</p>
      </div>"""
        
        safe_stripe_url = html.escape(stripe_url)
        
        return f"""
      <div class="payment-section">
        <h3 style="margin: 0 0 16px 0; color: #111827;">Pay Invoice Online</h3>
        <p style="color: #6b7280; margin: 0 0 16px 0;">Secure payment powered by Stripe</p>
        <a href="{safe_stripe_url}" class="payment-button">
          Pay ${amount:.2f} Now
        </a>
        <p style="font-size: 13px; color: #9ca3af; margin: 16px 0 0 0;">
          🔒 Your payment information is secure and encrypted
        </p>
      </div>"""
    
    @staticmethod
    def _get_status_badge(status: str) -> str:
        """Get HTML for status badge"""
        status_lower = status.lower()
        
        status_classes = {
            'paid': 'status-paid',
            'pending': 'status-pending',
            'overdue': 'status-overdue',
            'draft': 'status-draft',
        }
        
        css_class = status_classes.get(status_lower, 'status-pending')
        safe_status = html.escape(status)
        
        return f'<span class="status-badge {css_class}">{safe_status}</span>'

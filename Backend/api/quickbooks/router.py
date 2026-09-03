import asyncio
import logging
from datetime import datetime
from typing import Any

import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..auth import get_current_user
from .intuit_client import get_intuit_client_for_user
from .services.sync_service import QuickBooksSyncService
from ...config import settings
from ...models.user import User
from ...models.enums import UserType
from ...models.accounting.common import IntegrationType, IntegrationStatus
from ...database import get_session
from ...utils.datetime_utils import create_audit_datetime
from ...utils.recaptcha import require_recaptcha

from .utils import (
    check_rate_limit, get_user_integration,
    RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_HOURS,
    validate_quickbooks_configuration, check_quickbooks_connection_health
)
from .services import QuickBooksService, QuickBooksAuthService
from .services.expense_service import ExpenseService
from .services.invoice_service import InvoiceService
from .services.payment_service import PaymentService
from .services.account_mapping_service import AccountMappingService
from .services.webhook_service import QuickBooksWebhookService

logger = logging.getLogger(__name__)
router = APIRouter()

# API Models
class QuickBooksConnectionResponse(BaseModel):
    """
    Response model for QuickBooks connection initiation.
    
    Contains the connection status, user message, and optional redirect URL
    to complete the QuickBooks OAuth flow with Intuit.
    """
    status: str
    message: str
    redirect_url: str | None = None

class QuickBooksStatusResponse(BaseModel):
    """
    Response model for QuickBooks integration status.
    
    Provides current connection state, integration type, connection timestamps,
    and the company metadata if available.
    """
    connected: bool
    integration_type: str | None = None
    connected_at: datetime | None = None
    last_sync_at: datetime | None = None
    consumer_id: str | None = None

class QuickBooksSyncResponse(BaseModel):
    """
    Response model for QuickBooks synchronization operations.
    
    Contains sync success status, descriptive message, count of synced items,
    and any errors encountered during the synchronization process.
    """
    success: bool
    message: str
    items_synced: int | None = None
    errors: list[str] | None = None

class QuickBooksDisconnectResponse(BaseModel):
    """
    Response model for QuickBooks disconnection operation.

    Contains success status and message indicating whether the QuickBooks
    integration was successfully disconnected from the user account.
    """
    success: bool
    message: str

class SyncItemResponse(BaseModel):
    """Response model for a single sync item in preview."""
    entity_type: str
    entity_id: str
    entity_name: str
    action: str
    details: dict
    warnings: list[str] = []

class ApplySyncItem(BaseModel):
    """Payload model for applying selected sync operations."""
    entity_type: str
    entity_id: str
    action: str
    details: dict | None = None

class SyncPreviewResponse(BaseModel):
    """Response model for sync preview."""
    items: list[SyncItemResponse]
    summary: dict[str, int]
    warnings: list[str] = []

class QuickBooksAccountResponse(BaseModel):
    """Response model for QuickBooks account."""
    id: str
    name: str
    account_type: str
    account_sub_type: str | None = None
    active: bool


# Account Mapping Models
class AccountMappingResponse(BaseModel):
    """Response model for a QuickBooks account mapping."""
    id: int | None  # None for unpersisted mappings (e.g., auto-detected but not saved)
    mapping_type: str
    brikli_key: str
    quickbooks_account_id: str
    quickbooks_account_name: str
    quickbooks_account_type: str | None = None
    created_at: datetime
    updated_at: datetime


class AccountMappingCreate(BaseModel):
    """Request model for creating/updating an account mapping."""
    mapping_type: str  # tax_account, expense_account, etc.
    brikli_key: str  # GST, PST, HST, QST, etc.
    quickbooks_account_id: str
    quickbooks_account_name: str
    quickbooks_account_type: str | None = None


class AutoDetectMappingResponse(BaseModel):
    """Response model for auto-detected account mappings."""
    detected: dict[str, dict]  # tax_code -> account info
    saved: list[AccountMappingResponse]


# QuickBooks Settings Models
class QuickBooksSettings(BaseModel):
    """
    Settings schema stored in integrations.connection_metadata['settings'].

    Controls auto-sync behavior, entity sync scope, and notification preferences.
    All fields default to True for backward compatibility with existing users.
    """
    auto_sync_enabled: bool = True       # Enable webhook-triggered auto-sync
    sync_customers: bool = True          # Sync Customer entities
    sync_invoices: bool = True           # Sync Invoice entities
    sync_payments: bool = True           # Sync Payment entities
    sync_expenses: bool = True           # Sync Purchase/Expense entities
    notify_on_sync: bool = True          # Send in-app notifications on sync events


class QuickBooksConnectionHealth(BaseModel):
    """Connection health information for display in settings UI."""
    last_sync_at: datetime | None = None
    error_count: int = 0
    last_error: str | None = None


class QuickBooksSettingsResponse(BaseModel):
    """Response model for GET /settings endpoint."""
    settings: QuickBooksSettings
    connection_health: QuickBooksConnectionHealth


class QuickBooksSettingsUpdate(BaseModel):
    """
    Request model for PUT /settings endpoint.

    All fields are optional - only provided fields will be updated (partial update pattern).
    """
    auto_sync_enabled: bool | None = None
    sync_customers: bool | None = None
    sync_invoices: bool | None = None
    sync_payments: bool | None = None
    sync_expenses: bool | None = None
    notify_on_sync: bool | None = None


# API Endpoints
@router.get("/connect", response_model=QuickBooksConnectionResponse)
async def connect_to_quickbooks(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _recaptcha: None = Depends(require_recaptcha("quickbooks_connect"))
) -> QuickBooksConnectionResponse:
    """Initiate QuickBooks connection for authenticated user."""
    if not await check_rate_limit(str(current_user.id)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW_HOURS} hour(s)."
        )

    try:
        auth_service = QuickBooksAuthService(current_user, session)
        authorize_url, _ = await auth_service.build_authorize_url()

        return QuickBooksConnectionResponse(
            status="redirect_required",
            message="Please complete the connection process with Intuit",
            redirect_url=authorize_url,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating QuickBooks connection URL for user %s: %s", current_user.id, e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to initiate QuickBooks connection")

@router.get("/status", response_model=QuickBooksStatusResponse)
async def get_quickbooks_connection_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksStatusResponse:
    """Get QuickBooks integration status for authenticated user."""
    try:
        integration = await get_user_integration(current_user, session, IntegrationType.QUICKBOOKS)

        if not integration:
            return QuickBooksStatusResponse(
                connected=False,
                integration_type=None,
                connected_at=None,
                last_sync_at=None,
                consumer_id=None
            )

        return QuickBooksStatusResponse(
            connected=integration.status == IntegrationStatus.CONNECTED,
            integration_type=integration.integration_type.value,
            connected_at=integration.connected_at,
            last_sync_at=integration.last_sync_at,
            consumer_id=None
        )

    except Exception as e:
        logger.error("Error checking QuickBooks status for user %s: %s", current_user.id, e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to check QuickBooks status")


@router.get("/diagnostics")
async def get_quickbooks_diagnostics(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get detailed QuickBooks diagnostics for troubleshooting Error 3100 and other issues."""
    try:
        # Get basic status first
        integration = await get_user_integration(current_user, session, IntegrationType.QUICKBOOKS)
        
        
        diagnostics: dict[str, Any] = {
            "connected": integration and integration.status == IntegrationStatus.CONNECTED,
            "environment": settings.INTUIT_ENV,
            "scopes_configured": settings.INTUIT_SCOPES,
            "has_offline_access": "offline_access" in settings.INTUIT_SCOPES,
            "redirect_uri": settings.INTUIT_REDIRECT_URI,
            "integration_exists": integration is not None,
            "has_refresh_token": False
        }
        
        # Check if refresh token exists for connected integrations
        if integration and integration.status == IntegrationStatus.CONNECTED:
            from Backend.models.accounting.quickbooks_integration import QuickBooksIntegration
            qbi = await session.get(QuickBooksIntegration, integration.id)
            if qbi:
                diagnostics["has_refresh_token"] = bool(qbi.refresh_token_encrypted)
        
        # If connected, try a simple API call to verify authorization
        if integration and integration.status == IntegrationStatus.CONNECTED:
            try:
                from .intuit_client import get_intuit_client_for_user
                client = await get_intuit_client_for_user(current_user.id, session)
                # Try to get company info as a test
                company_info = await client.get_company_info()
                diagnostics["api_test"] = {
                    "success": True,
                    "company_name": company_info.get("CompanyInfo", {}).get("CompanyName"),
                    "company_id": company_info.get("CompanyInfo", {}).get("Id")
                }
            except HTTPException as e:
                diagnostics["api_test"] = {
                    "success": False,
                    "error": str(e.detail),
                    "status_code": e.status_code,
                    "is_3100_error": "3100" in str(e.detail) or "authorization failed" in str(e.detail).lower()
                }
            except Exception as e:
                diagnostics["api_test"] = {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
        
        return diagnostics
        
    except Exception as e:
        logger.error(f"Error getting QuickBooks diagnostics for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get diagnostics: {str(e)}"
        )


@router.post("/disconnect", response_model=QuickBooksDisconnectResponse)
async def disconnect_from_quickbooks(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksDisconnectResponse:
    """Disconnect QuickBooks integration for authenticated user."""
    try:
        auth_service = QuickBooksAuthService(current_user, session)
        result = await auth_service.disconnect_quickbooks()

        return QuickBooksDisconnectResponse(
            success=result["success"],
            message=result["message"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error disconnecting QuickBooks for user %s: %s", current_user.id, e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to disconnect QuickBooks")

@router.get("/callback", response_model=dict)
async def quickbooks_oauth_callback(
    code: str,
    realmId: str,
    state: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> dict:
    """Handle OAuth callback from QuickBooks after user authorization."""
    try:
        auth_service = QuickBooksAuthService(current_user, session)
        result = await auth_service.exchange_code_for_tokens(code, realmId, state)

        return {
            "success": True,
            "message": "Successfully connected to QuickBooks",
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in QuickBooks OAuth callback for user %s: %s", current_user.id, e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to complete QuickBooks connection")


@router.post("/initial-sync", response_model=QuickBooksSyncResponse)
async def initial_quickbooks_sync(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSyncResponse:
    """
    Performs an initial synchronization between the user's account and QuickBooks.

    This operation pulls and links customers, pushes any unlinked tenants, and imports all
    payments, invoices, and expenses from QuickBooks. Only available to landlords and admins.

    Returns:
        QuickBooksSyncResponse: Summary of the sync operation, including success status,
                               total items synced, and any errors encountered.
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords can perform initial sync."
        )

    # Verify QuickBooks connection exists
    integration = await get_user_integration(current_user, session, IntegrationType.QUICKBOOKS)
    if not integration or integration.status != IntegrationStatus.CONNECTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="QuickBooks must be connected before performing initial sync"
        )

    try:
        # Use the new sync service for clean, organized sync operations
        sync_service = QuickBooksSyncService(current_user, session)
        result = await sync_service.perform_initial_sync()

        return QuickBooksSyncResponse(
            success=result["success"],
            message=result["message"],
            items_synced=result["items_synced"],
            errors=result.get("errors")
        )

    except Exception as e:
        logger.error("Error during initial sync for user %s: %s", current_user.id, str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete initial synchronization"
        )

@router.post("/sync/payments", response_model=QuickBooksSyncResponse)
async def sync_payments_bidirectional(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSyncResponse:
    """
    Performs bidirectional payment synchronization between Brikli and QuickBooks.

    This operation:
    1. Pulls new/updated payments from QuickBooks into Brikli
    2. Pushes unsynced Brikli payments to QuickBooks

    Returns a summary with counts for both operations and any errors encountered.
    """

    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only landlords and admins can sync payments.")

    try:
        # Use the new sync service
        sync_service = QuickBooksSyncService(current_user, session)
        result = await sync_service.sync_payments()

        message = f"Bidirectional payment sync completed. Pulled {result.get('pulled_count', 0)}, pushed {result.get('pushed_count', 0)} payments."

        return QuickBooksSyncResponse(
            success=result["success"],
            message=message,
            items_synced=result["synced_count"],
            errors=result.get("errors")
        )

    except Exception as e:
        logger.error(f"Error during bidirectional payment sync for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete bidirectional payment sync"
        )

@router.post("/sync/invoices", response_model=QuickBooksSyncResponse)
async def sync_invoices_bidirectional(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSyncResponse:
    """
    Performs bidirectional invoice synchronization between Brikli and QuickBooks.

    This operation:
    1. Pulls new/updated invoices from QuickBooks into Brikli
    2. Pushes unsynced Brikli invoices to QuickBooks

    Returns a summary with counts for both operations and any errors encountered.
    """

    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only landlords and admins can sync invoices.")

    try:
        # Use the new sync service
        sync_service = QuickBooksSyncService(current_user, session)
        result = await sync_service.sync_invoices()

        message = f"Bidirectional invoice sync completed. Pulled {result.get('pulled_count', 0)}, pushed {result.get('pushed_count', 0)} invoices."

        return QuickBooksSyncResponse(
            success=result["success"],
            message=message,
            items_synced=result["synced_count"],
            errors=result.get("errors")
        )

    except Exception as e:
        logger.error(f"Error during bidirectional invoice sync for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete bidirectional invoice sync"
        )

@router.post("/sync/expenses", response_model=QuickBooksSyncResponse)
async def sync_expenses_bidirectional(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSyncResponse:
    """
    Performs bidirectional expense synchronization between Brikli and QuickBooks.

    This operation:
    1. Pulls new/updated expenses from QuickBooks into Brikli
    2. Pushes unsynced Brikli expenses to QuickBooks

    Returns a summary with counts for both operations and any errors encountered.
    """

    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only landlords and admins can sync expenses.")

    try:
        # Use the new sync service
        sync_service = QuickBooksSyncService(current_user, session)
        result = await sync_service.sync_expenses()

        message = f"Bidirectional expense sync completed. Pulled {result.get('pulled_count', 0)}, pushed {result.get('pushed_count', 0)} expenses."

        return QuickBooksSyncResponse(
            success=result["success"],
            message=message,
            items_synced=result["synced_count"],
            errors=result.get("errors")
        )

    except Exception as e:
        logger.error(f"Error during bidirectional expense sync for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete bidirectional expense sync"
        )


@router.post("/sync/all", response_model=QuickBooksSyncResponse)
async def sync_all_quickbooks_data(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSyncResponse:
    """
    Performs a comprehensive sync of all QuickBooks data.

    This endpoint synchronizes all supported data types (customers, payments,
    invoices, expenses) between QuickBooks and Brikli in both directions.

    Returns:
        QuickBooksSyncResponse: Summary of the unified sync operation with total items synced and any errors.
    """

    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only landlords and admins can perform sync operations.")

    try:
        # Use the new sync service for comprehensive sync
        sync_service = QuickBooksSyncService(current_user, session)
        result = await sync_service.perform_sync_all()

        return QuickBooksSyncResponse(
            success=result["success"],
            message=result["message"],
            items_synced=result["items_synced"],
            errors=result.get("errors")
        )

    except Exception as e:
        logger.error(f"Error during unified sync for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete unified sync"
        )


@router.post("/sync/transactions", response_model=QuickBooksSyncResponse)
async def sync_transactions_only(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSyncResponse:
    """
    Sync only transactions (expenses, invoices, payments) - skips customer sync.

    Use this endpoint after customers have already been linked via the wizard's
    first step. This is part of the progressive sync flow.

    Returns:
        QuickBooksSyncResponse: Summary of the transaction sync with items synced and any errors.
    """

    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only landlords and admins can perform sync operations.")

    try:
        sync_service = QuickBooksSyncService(current_user, session)
        result = await sync_service.perform_sync_transactions()

        return QuickBooksSyncResponse(
            success=result["success"],
            message=result["message"],
            items_synced=result["items_synced"],
            errors=result.get("errors")
        )

    except Exception as e:
        logger.error(f"Error during transaction sync for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete transaction sync"
        )


@router.get("/sync/preview", response_model=SyncPreviewResponse)
async def preview_quickbooks_sync(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> SyncPreviewResponse:
    """
    Preview what would happen during a QuickBooks sync operation.

    This endpoint performs a dry-run of the sync process and returns
    a detailed preview of what items would be created, updated, or skipped.
    No actual changes are made to the database.

    Returns:
        SyncPreviewResponse: Detailed preview of sync actions
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can preview sync operations."
        )

    try:
        # Get previews from all services
        expense_service = ExpenseService(current_user, session)
        invoice_service = InvoiceService(current_user, session)
        payment_service = PaymentService(current_user, session)
        from .services.customer_service import CustomerService
        customer_service = CustomerService(current_user, session, preview_mode=True)

        # Run all previews
        expense_preview = await expense_service.preview_expenses()
        invoice_preview = await invoice_service.preview_invoices()
        payment_preview = await payment_service.preview_payments()
        customer_preview = await customer_service.preview_customers()

        # Combine all items
        all_items = (
            expense_preview.items +
            invoice_preview.items +
            payment_preview.items +
            customer_preview.items
        )

        # Combine summaries
        combined_summary = {
            "create": sum([
                expense_preview.summary.get("create", 0),
                invoice_preview.summary.get("create", 0),
                payment_preview.summary.get("create", 0),
                customer_preview.summary.get("create", 0)
            ]),
            "update": sum([
                expense_preview.summary.get("update", 0),
                invoice_preview.summary.get("update", 0),
                payment_preview.summary.get("update", 0),
                customer_preview.summary.get("update", 0)
            ]),
            "skip": sum([
                expense_preview.summary.get("skip", 0),
                invoice_preview.summary.get("skip", 0),
                payment_preview.summary.get("skip", 0),
                customer_preview.summary.get("skip", 0)
            ]),
            "error": sum([
                expense_preview.summary.get("error", 0),
                invoice_preview.summary.get("error", 0),
                payment_preview.summary.get("error", 0),
                customer_preview.summary.get("error", 0)
            ]),
            "total": len(all_items)
        }

        # Combine warnings - handle Optional[List[str]] from preview objects
        expense_warnings: list[str] = list(expense_preview.warnings) if expense_preview.warnings else []
        invoice_warnings: list[str] = list(invoice_preview.warnings) if invoice_preview.warnings else []
        payment_warnings: list[str] = list(payment_preview.warnings) if payment_preview.warnings else []
        customer_warnings: list[str] = list(customer_preview.warnings) if customer_preview.warnings else []
        combined_warnings: list[str] = expense_warnings + invoice_warnings + payment_warnings + customer_warnings

        # Convert preview to response model
        items = [
            SyncItemResponse(
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                entity_name=item.entity_name,
                action=item.action.value,
                details=item.details,
                warnings=item.warnings or []
            )
            for item in all_items
        ]

        return SyncPreviewResponse(
            items=items,
            summary=combined_summary,
            warnings=combined_warnings
        )

    except Exception as e:
        logger.error(f"Error during sync preview for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate sync preview"
        )


@router.get("/accounts", response_model=list[QuickBooksAccountResponse])
async def list_quickbooks_accounts(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> list[QuickBooksAccountResponse]:
    """
    List all accounts from the connected QuickBooks company.

    Returns all chart of accounts entries that can be used for mapping
    categories and configuring default accounts.

    Returns:
        list[QuickBooksAccountResponse]: List of QuickBooks accounts
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can access QuickBooks accounts."
        )

    try:
        # Verify QuickBooks connection
        integration = await get_user_integration(current_user, session, IntegrationType.QUICKBOOKS)
        if not integration or integration.status != IntegrationStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QuickBooks must be connected to list accounts"
            )

        # Use AccountMappingService which has session-level caching
        # This avoids repeated API calls when the UI fetches accounts multiple times
        from .services.account_mapping_service import AccountMappingService
        mapping_service = AccountMappingService(current_user, session)
        accounts = await mapping_service.fetch_all_accounts_from_qb()

        # Convert to response models
        result = []
        for account in accounts:
            result.append(QuickBooksAccountResponse(
                id=account.get("Id", ""),
                name=account.get("Name", ""),
                account_type=account.get("AccountType", ""),
                account_sub_type=account.get("AccountSubType"),
                active=account.get("Active", True)
            ))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing QuickBooks accounts for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list QuickBooks accounts"
        )


# === Account Mapping Endpoints ===

@router.get("/accounts/mappings", response_model=list[AccountMappingResponse])
async def get_account_mappings(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> list[AccountMappingResponse]:
    """
    Get all account mappings for the current user's QuickBooks integration.

    Returns the mappings between Brikli tax types (GST, HST, PST, QST) and
    QuickBooks account IDs.
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can access account mappings."
        )

    try:
        mapping_service = AccountMappingService(current_user, session)
        mappings = await mapping_service.get_all_mappings()

        return [
            AccountMappingResponse(
                id=m.id if m.id is not None else 0,
                mapping_type=m.mapping_type,
                brikli_key=m.brikli_key,
                quickbooks_account_id=m.quickbooks_account_id,
                quickbooks_account_name=m.quickbooks_account_name,
                quickbooks_account_type=m.quickbooks_account_type,
                created_at=m.created_at,
                updated_at=m.updated_at
            )
            for m in mappings
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting account mappings for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get account mappings"
        )


@router.post("/accounts/mappings", response_model=AccountMappingResponse)
async def save_account_mapping(
    mapping: AccountMappingCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> AccountMappingResponse:
    """
    Save or update an account mapping.

    Maps a Brikli tax type (e.g., GST, PST) to a QuickBooks account ID.
    This is essential for proper tax line detection during expense sync.
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can modify account mappings."
        )

    try:
        mapping_service = AccountMappingService(current_user, session)
        saved = await mapping_service.save_account_mapping(
            mapping_type=mapping.mapping_type,
            brikli_key=mapping.brikli_key,
            quickbooks_account_id=mapping.quickbooks_account_id,
            quickbooks_account_name=mapping.quickbooks_account_name,
            quickbooks_account_type=mapping.quickbooks_account_type
        )

        return AccountMappingResponse(
            id=saved.id if saved.id is not None else 0,
            mapping_type=saved.mapping_type,
            brikli_key=saved.brikli_key,
            quickbooks_account_id=saved.quickbooks_account_id,
            quickbooks_account_name=saved.quickbooks_account_name,
            quickbooks_account_type=saved.quickbooks_account_type,
            created_at=saved.created_at,
            updated_at=saved.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving account mapping for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save account mapping"
        )


@router.post("/accounts/mappings/auto-detect", response_model=AutoDetectMappingResponse)
async def auto_detect_account_mappings(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> AutoDetectMappingResponse:
    """
    Auto-detect Canadian tax accounts from QuickBooks Chart of Accounts.

    Scans the user's QuickBooks accounts and attempts to match them to
    Canadian tax types (GST, HST, PST, QST) based on common naming patterns.
    Detected mappings are automatically saved.

    This fixes the "No tax details found" warning by establishing proper
    mappings between tax codes and QuickBooks account IDs.
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can auto-detect account mappings."
        )

    try:
        mapping_service = AccountMappingService(current_user, session)

        # First, detect without saving to return the detected mappings
        detected = await mapping_service.auto_detect_tax_accounts()

        # Then save them
        saved_mappings = await mapping_service.save_auto_detected_mappings()

        return AutoDetectMappingResponse(
            detected=detected,
            saved=[
                AccountMappingResponse(
                    id=m.id if m.id is not None else 0,
                    mapping_type=m.mapping_type,
                    brikli_key=m.brikli_key,
                    quickbooks_account_id=m.quickbooks_account_id,
                    quickbooks_account_name=m.quickbooks_account_name,
                    quickbooks_account_type=m.quickbooks_account_type,
                    created_at=m.created_at,
                    updated_at=m.updated_at
                )
                for m in saved_mappings
            ]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error auto-detecting account mappings for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to auto-detect account mappings"
        )


@router.delete("/accounts/mappings/{mapping_id}")
async def delete_account_mapping(
    mapping_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> dict:
    """
    Delete an account mapping by ID.
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can delete account mappings."
        )

    try:
        mapping_service = AccountMappingService(current_user, session)
        deleted = await mapping_service.delete_account_mapping(mapping_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account mapping {mapping_id} not found"
            )

        return {"status": "success", "message": f"Account mapping {mapping_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting account mapping {mapping_id} for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account mapping"
        )


@router.get("/accounts/tax-eligible", response_model=list[QuickBooksAccountResponse])
async def get_tax_eligible_accounts(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> list[QuickBooksAccountResponse]:
    """
    Get QuickBooks accounts that are eligible for tax mapping.

    Filters the Chart of Accounts to only include expense-type accounts
    that are commonly used for tracking taxes paid on purchases.
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can access tax-eligible accounts."
        )

    try:
        mapping_service = AccountMappingService(current_user, session)
        accounts = await mapping_service.get_tax_accounts()

        return [
            QuickBooksAccountResponse(
                id=a["id"],
                name=a["name"],
                account_type=a["account_type"],
                account_sub_type=None,
                active=a.get("active", True)
            )
            for a in accounts
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tax-eligible accounts for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get tax-eligible accounts"
        )


# Settings Endpoints
def _get_settings_from_integration(integration) -> QuickBooksSettings:
    """Extract settings from connection_metadata with defaults."""
    if not integration or not integration.connection_metadata:
        return QuickBooksSettings()
    settings_data = integration.connection_metadata.get('settings', {})
    return QuickBooksSettings(**settings_data)


def _get_connection_health(integration) -> QuickBooksConnectionHealth:
    """Build connection health info from integration."""
    if not integration:
        return QuickBooksConnectionHealth()
    return QuickBooksConnectionHealth(
        last_sync_at=integration.last_sync_at,
        error_count=integration.error_count or 0,
        last_error=integration.last_error
    )


@router.get("/settings", response_model=QuickBooksSettingsResponse)
async def get_quickbooks_settings(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSettingsResponse:
    """
    Get QuickBooks integration settings for the current user.

    Returns settings from connection_metadata['settings'] with sensible defaults,
    plus connection health information (last sync, errors).

    Settings control:
    - auto_sync_enabled: Whether webhooks trigger automatic sync
    - sync_customers/invoices/payments/expenses: Which entity types to sync
    - notify_on_sync: Whether to send in-app notifications on sync events
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can access QuickBooks settings."
        )

    try:
        integration = await get_user_integration(current_user, session, IntegrationType.QUICKBOOKS)

        if not integration or integration.status != IntegrationStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QuickBooks is not connected. Please connect first."
            )

        settings = _get_settings_from_integration(integration)
        connection_health = _get_connection_health(integration)

        return QuickBooksSettingsResponse(
            settings=settings,
            connection_health=connection_health
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting QuickBooks settings for user {current_user.id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get QuickBooks settings"
        )


@router.put("/settings", response_model=QuickBooksSettingsResponse)
async def update_quickbooks_settings(
    settings_update: QuickBooksSettingsUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSettingsResponse:
    """
    Update QuickBooks integration settings.

    Merges provided fields with existing settings in connection_metadata['settings'].
    Only updates fields that are explicitly provided (partial update pattern).

    Example: To disable auto-sync but keep other settings:
    PUT /settings {"auto_sync_enabled": false}
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can update QuickBooks settings."
        )

    try:
        integration = await get_user_integration(current_user, session, IntegrationType.QUICKBOOKS)

        if not integration or integration.status != IntegrationStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QuickBooks is not connected. Please connect first."
            )

        # Get existing settings with defaults
        current_settings = _get_settings_from_integration(integration)

        # Merge with updates (only non-None fields)
        update_data = settings_update.model_dump(exclude_none=True)
        merged_settings = current_settings.model_dump()
        merged_settings.update(update_data)

        # Save to connection_metadata
        # Create a new dict to ensure SQLAlchemy detects the change
        metadata = dict(integration.connection_metadata or {})
        metadata['settings'] = merged_settings
        integration.connection_metadata = metadata
        # Explicitly flag the JSONB column as modified for SQLAlchemy
        flag_modified(integration, 'connection_metadata')

        session.add(integration)
        await session.commit()
        await session.refresh(integration)

        logger.info(f"Updated QuickBooks settings for user {current_user.id}: {update_data}")

        # Return updated settings
        settings = QuickBooksSettings(**merged_settings)
        connection_health = _get_connection_health(integration)

        return QuickBooksSettingsResponse(
            settings=settings,
            connection_health=connection_health
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating QuickBooks settings for user {current_user.id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update QuickBooks settings"
        )


class QuickBooksValidationResponse(BaseModel):
    """Response model for QuickBooks configuration validation."""
    is_valid: bool
    missing_config: list[str]
    warnings: list[str]
    account_info: dict
    item_info: dict
    company_info: dict | None = None


class QuickBooksHealthResponse(BaseModel):
    """Response model for QuickBooks connection health check."""
    is_healthy: bool
    status: str
    last_checked: str
    issues: list[str]
    metrics: dict
    recommendations: list[str]


@router.get("/validate", response_model=QuickBooksValidationResponse)
async def validate_quickbooks_configuration_endpoint(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksValidationResponse:
    """
    Validates the QuickBooks integration configuration for the current user.

    Checks if all required components are properly configured:
    - Active QuickBooks connection
    - Default bank/credit card account for expenses
    - Default expense category account
    - Default service item for invoices

    Returns detailed validation results with suggestions for missing configuration.
    """
    if current_user.user_type != UserType.LANDLORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords can validate QuickBooks configuration"
        )

    try:
        validation_result = await validate_quickbooks_configuration(current_user, session)

        return QuickBooksValidationResponse(
            is_valid=validation_result["is_valid"],
            missing_config=validation_result["missing_config"],
            warnings=validation_result["warnings"],
            account_info=validation_result["account_info"],
            item_info=validation_result["item_info"],
            company_info=validation_result.get("company_info")
        )
    except Exception as e:
        logger.error(f"Error validating QuickBooks configuration for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate QuickBooks configuration"
        )

@router.post("/sync/apply", response_model=QuickBooksSyncResponse)
async def apply_quickbooks_sync(
    items: list[ApplySyncItem],
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> QuickBooksSyncResponse:
    """
    Apply selected sync operations from the preview (customer link/create/update only).

    Frontend sends selected items; we perform the confirmed operations and return a summary.
    """
    if current_user.user_type != UserType.LANDLORD and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords and admins can apply sync operations."
        )

    try:
        from .services.customer_service import CustomerService

        customer_service = CustomerService(current_user, session)
        await customer_service.initialize()

        total = 0
        errors: list[str] = []

        for item in items:
            try:
                # Validate entity type/action before processing
                valid_types = {"customer_link", "customer_create", "customer_update"}
                valid_actions = {"create", "update"}
                
                if item.entity_type not in valid_types:
                    errors.append(f"Invalid entity_type: {item.entity_type}. Expected one of: {', '.join(valid_types)}")
                    continue
                
                if item.action not in valid_actions:
                    errors.append(f"Invalid action: {item.action}. Expected one of: {', '.join(valid_actions)}")
                    continue

                if item.entity_type in {"customer_link", "customer_create"} and item.action in {"create", "update"}:
                    tenant_id = int(item.entity_id)
                    from ...models.tenant import Tenant as TenantModel
                    tenant = await session.get(TenantModel, tenant_id)
                    if not tenant:
                        errors.append(f"Tenant {tenant_id} not found")
                        continue

                    if item.entity_type == "customer_link":
                        qb_customer_id = (item.details or {}).get("qb_customer_id")
                        if not qb_customer_id:
                            errors.append(f"Missing qb_customer_id for tenant {tenant_id}")
                            continue

                        # Idempotency check: Skip if already linked to this QB customer
                        if tenant.quickbooks_customer_id == qb_customer_id:
                            logger.info(f"Tenant {tenant_id} already linked to QuickBooks customer {qb_customer_id}, skipping")
                            total += 1  # Count as successful (no-op)
                            continue

                        # Check if another tenant is already using this QuickBooks customer ID
                        from sqlmodel import select, col
                        existing_link = await session.scalar(
                            select(TenantModel).where(
                                col(TenantModel.landlord_id) == current_user.id,
                                col(TenantModel.quickbooks_customer_id) == qb_customer_id,
                                col(TenantModel.id) != tenant_id
                            )
                        )
                        if existing_link:
                            errors.append(f"QuickBooks customer {qb_customer_id} is already linked to another tenant (ID: {existing_link.id})")
                            continue

                        tenant.quickbooks_customer_id = qb_customer_id
                        tenant.last_synced_at = create_audit_datetime()
                        session.add(tenant)
                        total += 1
                        logger.info(f"Linked tenant {tenant_id} to QuickBooks customer {qb_customer_id}")
                    elif item.entity_type == "customer_create":
                        # Idempotency check: Skip if tenant already has a QB customer ID
                        if tenant.quickbooks_customer_id:
                            logger.info(f"Tenant {tenant_id} already has QuickBooks customer ID {tenant.quickbooks_customer_id}, skipping create")
                            total += 1  # Count as successful (no-op)
                            continue

                        # Check if customer already exists by email
                        if tenant.email:
                            existing_customer_id = await customer_service._find_existing_customer_by_email(tenant.email)
                            if existing_customer_id:
                                # Found a customer in QB. Check if it's already linked to another tenant.
                                from sqlmodel import select, col
                                existing_link = await session.scalar(
                                    select(TenantModel).where(
                                        col(TenantModel.landlord_id) == current_user.id,
                                        col(TenantModel.quickbooks_customer_id) == existing_customer_id
                                    )
                                )
                                if existing_link:
                                    errors.append(f"A QuickBooks customer with email '{tenant.email}' already exists and is linked to another tenant (ID: {existing_link.id})")
                                    continue

                                # Link to existing customer instead of creating new one
                                tenant.quickbooks_customer_id = existing_customer_id
                                tenant.last_synced_at = create_audit_datetime()
                                session.add(tenant)
                                total += 1
                                logger.info(f"Linked tenant {tenant_id} to existing QuickBooks customer {existing_customer_id} (found by email)")
                                continue

                        # Create new customer
                        created_id = await customer_service._create_customer_in_quickbooks(tenant)
                        if created_id:
                            tenant.quickbooks_customer_id = created_id
                            tenant.last_synced_at = create_audit_datetime()
                            session.add(tenant)
                            total += 1
                            logger.info(f"Created QuickBooks customer {created_id} for tenant {tenant_id}")
                        else:
                            errors.append(f"Failed to create QuickBooks customer for tenant {tenant_id}")
                elif item.entity_type == "customer_update" and item.action == "update":
                    tenant_id = int(item.entity_id)
                    from ...models.tenant import Tenant as TenantModel
                    tenant = await session.get(TenantModel, tenant_id)
                    if not tenant:
                        errors.append(f"Tenant {tenant_id} not found")
                        continue
                    success = await customer_service.update_customer_in_quickbooks(tenant)
                    if success:
                        total += 1
                    else:
                        errors.append(f"Failed to update QuickBooks customer for tenant {tenant_id}")
            except Exception as e:
                error_msg = f"Error processing {item.entity_type} for tenant {item.entity_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg, exc_info=True)
                # Capture in Sentry with context
                sentry_sdk.capture_exception(e, extras={
                    "entity_type": item.entity_type,
                    "entity_id": item.entity_id,
                    "action": item.action,
                    "user_id": str(current_user.id),
                    "details": item.details
                })

        # Atomic behavior: if any errors occurred, roll back the entire batch
        if errors:
            await session.rollback()
            return QuickBooksSyncResponse(
                success=False,
                message=f"Failed to apply operations. {len(errors)} error(s) occurred. No changes were saved.",
                items_synced=0,
                errors=errors
            )

        if total > 0:
            await session.commit()

        return QuickBooksSyncResponse(
            success=True,
            message=f"Successfully applied {total} customer operations.",
            items_synced=total,
            errors=None
        )

    except Exception as e:
        logger.error(f"Error applying QuickBooks sync for user {current_user.id}: {e}", exc_info=True)
        # Capture in Sentry with context
        sentry_sdk.capture_exception(e, extras={
            "user_id": str(current_user.id),
            "items_count": len(items),
            "operation": "apply_quickbooks_sync"
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply sync operations"
        )


@router.get("/health", response_model=QuickBooksHealthResponse)
async def check_quickbooks_health(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    deep_check: bool = False
) -> QuickBooksHealthResponse:
    """
    Check the health of the QuickBooks integration connection.

    Performs various health checks including configuration validation,
    error count monitoring, and optional API connectivity testing.

    Args:
        deep_check: Whether to perform API calls to verify connectivity (slower but more thorough)

    Returns:
        QuickBooksHealthResponse with health status, issues, and recommendations
    """
    if current_user.user_type != UserType.LANDLORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords can check QuickBooks health"
        )

    try:
        health_status = await check_quickbooks_connection_health(
            current_user, session, perform_deep_check=deep_check
        )

        return QuickBooksHealthResponse(**health_status)

    except Exception as e:
        logger.error(f"Error checking QuickBooks health for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check QuickBooks health"
        )


# === Monitoring and Circuit Breaker Endpoints ===

class CircuitBreakerStatsResponse(BaseModel):
    """Response model for circuit breaker statistics."""
    circuit_breakers: dict[str, Any]
    global_stats: dict[str, Any]


class TransactionStatsResponse(BaseModel):
    """Response model for transaction coordinator statistics."""
    message: str
    note: str


@router.get("/monitoring/circuit-breakers", response_model=CircuitBreakerStatsResponse)
async def get_circuit_breaker_stats(
    current_user: User = Depends(get_current_user)
) -> CircuitBreakerStatsResponse:
    """
    Get circuit breaker statistics for monitoring.

    Returns current state and statistics for all QuickBooks circuit breakers.
    Useful for monitoring system health and failure patterns.
    """
    if current_user.user_type != UserType.LANDLORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords can access monitoring endpoints"
        )

    try:
        from .circuit_breaker import get_all_circuit_breaker_stats

        stats = await get_all_circuit_breaker_stats()

        # Calculate global statistics
        global_stats = {
            "total_circuit_breakers": len(stats),
            "open_circuits": sum(1 for cb_stats in stats.values() if cb_stats["state"] == "open"),
            "half_open_circuits": sum(1 for cb_stats in stats.values() if cb_stats["state"] == "half_open"),
            "closed_circuits": sum(1 for cb_stats in stats.values() if cb_stats["state"] == "closed"),
            "total_requests": sum(cb_stats["total_requests"] for cb_stats in stats.values()),
            "total_failures": sum(cb_stats["total_failures"] for cb_stats in stats.values()),
            "average_failure_rate": sum(cb_stats["failure_rate"] for cb_stats in stats.values()) / len(stats) if stats else 0
        }

        return CircuitBreakerStatsResponse(
            circuit_breakers=stats,
            global_stats=global_stats
        )

    except Exception as e:
        logger.error(f"Error getting circuit breaker stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve circuit breaker statistics"
        )




@router.post("/monitoring/reset-circuit-breaker/{circuit_name}")
async def reset_circuit_breaker(
    circuit_name: str,
    current_user: User = Depends(get_current_user)
) -> dict[str, str]:
    """
    Manually reset a specific circuit breaker to closed state.

    This is an admin function to recover from circuit breaker failures
    when the underlying issue has been resolved.
    """
    if current_user.user_type != UserType.LANDLORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords can reset circuit breakers"
        )

    try:
        from .circuit_breaker import get_circuit_breaker

        circuit_breaker = await get_circuit_breaker(circuit_name)
        await circuit_breaker.reset()

        logger.info(f"Circuit breaker '{circuit_name}' manually reset by user {current_user.id}")

        return {
            "status": "success",
            "message": f"Circuit breaker '{circuit_name}' has been reset to closed state"
        }

    except Exception as e:
        logger.error(f"Error resetting circuit breaker '{circuit_name}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset circuit breaker '{circuit_name}'"
        )




@router.get("/monitoring/transactions", response_model=TransactionStatsResponse)
async def get_transaction_stats(
    current_user: User = Depends(get_current_user)
) -> TransactionStatsResponse:
    """
    Get transaction coordinator statistics.

    Note: Individual transaction statistics are logged but not persisted
    for performance reasons. This endpoint provides general information
    about the transaction coordinator system.
    """
    if current_user.user_type != UserType.LANDLORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords can access monitoring endpoints"
        )

    return TransactionStatsResponse(
        message="Transaction coordinator monitoring is event-based",
        note="Check application logs and Sentry for detailed transaction statistics and failure analysis"
    )


# === QuickBooks Webhooks ===

class WebhookResponse(BaseModel):
    """Response model for webhook processing."""
    success: bool
    message: str
    processed: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


@router.post("/webhooks", response_model=WebhookResponse)
async def handle_quickbooks_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session)
) -> WebhookResponse:
    """
    Handle incoming webhook notifications from QuickBooks Online.

    This endpoint receives real-time notifications when data changes in QuickBooks.
    It automatically syncs the affected entities to Brikli's database.

    Security:
    - Verifies the webhook signature using HMAC-SHA256
    - Only processes events for users with active QuickBooks connections

    Supported Entity Types:
    - Customer: Updates linked Tenant records
    - Invoice: Syncs invoice data
    - Payment: Syncs payment data
    - Purchase: Syncs expense data

    Supported Operations:
    - Create: New entity created in QuickBooks
    - Update: Existing entity updated in QuickBooks
    - Delete: Entity deleted in QuickBooks
    - Void: Entity voided in QuickBooks

    Note: This endpoint does NOT require authentication as it's called by QuickBooks.
    Security is ensured via signature verification.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Get signature header
        signature = request.headers.get("intuit-signature", "")

        if not signature:
            logger.warning("Webhook received without signature header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing webhook signature"
            )

        # Verify signature
        if not QuickBooksWebhookService.verify_signature(body, signature):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )

        # Parse payload
        try:
            payload = await request.json()
        except Exception as e:
            logger.error(f"Failed to parse webhook payload: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )

        logger.info(f"Received QuickBooks webhook: {len(payload.get('eventNotifications', []))} notifications")

        # Process the webhook
        webhook_service = QuickBooksWebhookService(session)
        result = await webhook_service.process_webhook(payload)

        return WebhookResponse(
            success=len(result["errors"]) == 0,
            message=f"Processed {result['processed']} events, skipped {result['skipped']}",
            processed=result["processed"],
            skipped=result["skipped"],
            errors=result["errors"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing QuickBooks webhook: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )


@router.get("/webhooks/verify")
async def verify_webhook_endpoint() -> dict:
    """
    Verification endpoint for QuickBooks webhook setup.

    When you configure a webhook in the Intuit Developer Portal,
    QuickBooks will send a verification request to ensure your endpoint is reachable.

    This endpoint simply returns a success response to pass the verification check.
    """
    return {"status": "ok", "message": "Webhook endpoint verified"}


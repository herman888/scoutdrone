"""
Integration tests for multi-unit tenant assignment feature.

Tests the industry-standard approach where a single tenant can have multiple 
active leases for different units (e.g., apartment + parking + storage),
while preventing double-booking (same tenant + same unit + overlapping dates).

Industry Standards (Yardi, AppFolio, Buildium):
- ✅ Allow: Same tenant + Different units = Multiple active leases
- ❌ Block: Same tenant + Same unit + Overlapping dates = Conflict
"""

import pytest
import logging
import httpx
from datetime import datetime, timedelta, timezone

from .conftest import assert_valid_json_response, assert_api_error

logger = logging.getLogger(__name__)


@pytest.mark.auth
@pytest.mark.integration
@pytest.mark.asyncio
async def test_tenant_can_have_multiple_units(
    api_client: httpx.AsyncClient,
    created_landlord_property: int,
    created_tenant: dict
):
    """
    Test that a tenant can have multiple active leases for different units.
    This is the industry standard approach (apartment + parking + storage).
    """
    logger.info("Testing multi-unit tenant assignment...")
    
    # Create three units: apartment, parking, storage
    unit_apartment_data = {
        "property_id": created_landlord_property,
        "name": "Apartment 101",
        "unit_type": "Unit",
        "monthly_rent": "1500.00"
    }
    response = await api_client.post("/api/units/", json=unit_apartment_data)
    unit_apartment = assert_valid_json_response(response, dict, 201)
    
    unit_parking_data = {
        "property_id": created_landlord_property,
        "name": "Parking P5",
        "unit_type": "Parking",
        "monthly_rent": "100.00"
    }
    response = await api_client.post("/api/units/", json=unit_parking_data)
    unit_parking = assert_valid_json_response(response, dict, 201)
    
    unit_storage_data = {
        "property_id": created_landlord_property,
        "name": "Storage S12",
        "unit_type": "Storage",
        "monthly_rent": "50.00"
    }
    response = await api_client.post("/api/units/", json=unit_storage_data)
    unit_storage = assert_valid_json_response(response, dict, 201)
    
    # Create lease #1: Apartment
    lease1_data = {
        "property_id": created_landlord_property,
        "unit_id": unit_apartment["id"],
        "tenant_id": created_tenant["id"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "monthly_rent": "1500.00",
        "security_deposit": "1500.00",
        "status": "ACTIVE"
    }
    response = await api_client.post("/api/leases/", json=lease1_data)
    lease1 = assert_valid_json_response(response, dict, 201)
    logger.info(f"✅ Created lease #1 (Apartment) for tenant {created_tenant['id']}")
    
    # Create lease #2: Parking (same tenant, different unit)
    lease2_data = {
        "property_id": created_landlord_property,
        "unit_id": unit_parking["id"],
        "tenant_id": created_tenant["id"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "monthly_rent": "100.00",
        "security_deposit": "100.00",
        "status": "ACTIVE"
    }
    response = await api_client.post("/api/leases/", json=lease2_data)
    lease2 = assert_valid_json_response(response, dict, 201)
    logger.info(f"✅ Created lease #2 (Parking) for tenant {created_tenant['id']}")
    
    # Create lease #3: Storage (same tenant, different unit)
    lease3_data = {
        "property_id": created_landlord_property,
        "unit_id": unit_storage["id"],
        "tenant_id": created_tenant["id"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "monthly_rent": "50.00",
        "security_deposit": "50.00",
        "status": "ACTIVE"
    }
    response = await api_client.post("/api/leases/", json=lease3_data)
    lease3 = assert_valid_json_response(response, dict, 201)
    logger.info(f"✅ Created lease #3 (Storage) for tenant {created_tenant['id']}")
    
    # Verify all three leases exist for the same tenant
    response = await api_client.get(f"/api/leases/?tenant_id={created_tenant['id']}")
    tenant_leases = assert_valid_json_response(response, list)
    
    active_leases = [l for l in tenant_leases if l["status"] == "ACTIVE"]
    assert len(active_leases) >= 3, f"Expected at least 3 active leases, got {len(active_leases)}"
    
    # Verify each unit is assigned to different lease
    lease_unit_ids = {l["unit_id"] for l in active_leases}
    assert unit_apartment["id"] in lease_unit_ids
    assert unit_parking["id"] in lease_unit_ids
    assert unit_storage["id"] in lease_unit_ids
    
    logger.info("✅ MULTI-UNIT ASSIGNMENT SUCCESS: Tenant has 3 active leases for different units")
    
    # Cleanup
    await api_client.delete(f"/api/leases/{lease1['id']}")
    await api_client.delete(f"/api/leases/{lease2['id']}")
    await api_client.delete(f"/api/leases/{lease3['id']}")
    await api_client.delete(f"/api/units/{unit_apartment['id']}")
    await api_client.delete(f"/api/units/{unit_parking['id']}")
    await api_client.delete(f"/api/units/{unit_storage['id']}")


@pytest.mark.auth
@pytest.mark.integration
@pytest.mark.asyncio
async def test_prevent_double_booking_same_unit(
    api_client: httpx.AsyncClient,
    created_landlord_property: int,
    created_unit: dict,
    created_tenant: dict
):
    """
    Test that double-booking is prevented: same tenant + same unit + overlapping dates.
    This should be blocked to prevent conflicts.
    """
    logger.info("Testing double-booking prevention...")
    
    # Create first lease for the unit
    lease1_data = {
        "property_id": created_landlord_property,
        "unit_id": created_unit["id"],
        "tenant_id": created_tenant["id"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "monthly_rent": "1500.00",
        "security_deposit": "1500.00",
        "status": "ACTIVE"
    }
    response = await api_client.post("/api/leases/", json=lease1_data)
    lease1 = assert_valid_json_response(response, dict, 201)
    logger.info(f"✅ Created first lease for unit {created_unit['id']}")
    
    # Try to create second lease for SAME tenant + SAME unit with overlapping dates
    lease2_data = {
        "property_id": created_landlord_property,
        "unit_id": created_unit["id"],  # Same unit
        "tenant_id": created_tenant["id"],  # Same tenant
        "start_date": "2024-06-01",  # Overlaps with first lease
        "end_date": "2025-06-01",
        "monthly_rent": "1600.00",
        "security_deposit": "1600.00",
        "status": "ACTIVE"
    }
    response = await api_client.post("/api/leases/", json=lease2_data)
    
    # This should fail with 400 Bad Request
    assert response.status_code == 400, f"Expected 400 error, got {response.status_code}"
    error_data = response.json()
    assert "overlapping dates" in error_data["detail"].lower(), \
        f"Expected overlapping dates error, got: {error_data['detail']}"
    
    logger.info("✅ DOUBLE-BOOKING PREVENTED: Cannot create overlapping lease for same tenant+unit")
    
    # Cleanup
    await api_client.delete(f"/api/leases/{lease1['id']}")


@pytest.mark.auth
@pytest.mark.integration
@pytest.mark.asyncio
async def test_tenant_can_renew_lease_after_expiry(
    api_client: httpx.AsyncClient,
    created_landlord_property: int,
    created_unit: dict,
    created_tenant: dict
):
    """
    Test that a tenant can have a new lease for the same unit after the previous one expires.
    This should be allowed since the dates don't overlap.
    """
    logger.info("Testing lease renewal (non-overlapping dates)...")
    
    # Create first lease (Jan-Dec 2024)
    lease1_data = {
        "property_id": created_landlord_property,
        "unit_id": created_unit["id"],
        "tenant_id": created_tenant["id"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "monthly_rent": "1500.00",
        "security_deposit": "1500.00",
        "status": "EXPIRED"  # Marking as expired
    }
    response = await api_client.post("/api/leases/", json=lease1_data)
    lease1 = assert_valid_json_response(response, dict, 201)
    logger.info(f"✅ Created first lease (2024)")
    
    # Create renewal lease for SAME unit (Jan-Dec 2025) - no overlap
    lease2_data = {
        "property_id": created_landlord_property,
        "unit_id": created_unit["id"],  # Same unit
        "tenant_id": created_tenant["id"],  # Same tenant
        "start_date": "2025-01-01",  # Starts after first ends
        "end_date": "2025-12-31",
        "monthly_rent": "1600.00",  # Higher rent
        "security_deposit": "1600.00",
        "status": "ACTIVE"
    }
    response = await api_client.post("/api/leases/", json=lease2_data)
    lease2 = assert_valid_json_response(response, dict, 201)
    logger.info(f"✅ Created renewal lease (2025)")
    
    # Both leases should exist
    response = await api_client.get(f"/api/leases/?tenant_id={created_tenant['id']}")
    tenant_leases = assert_valid_json_response(response, list)
    assert len(tenant_leases) >= 2
    
    logger.info("✅ LEASE RENEWAL SUCCESS: Same tenant+unit with non-overlapping dates allowed")
    
    # Cleanup
    await api_client.delete(f"/api/leases/{lease1['id']}")
    await api_client.delete(f"/api/leases/{lease2['id']}")

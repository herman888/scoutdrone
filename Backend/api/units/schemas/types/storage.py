"""
Storage/Locker unit type-specific detail schemas.
For storage units and lockers.
"""
from typing import Literal, Optional
from pydantic import Field

from .base import UnitTypeDetailsBase


class StorageUnitDetails(UnitTypeDetailsBase):
    """Base storage/locker unit details with common fields."""
    
    unit_type: Literal['Locker', 'Storage'] = Field(
        'Storage',
        description="Either 'Locker' for small storage or 'Storage' for larger units"
    )
    
    # Storage-specific fields
    locker_number: Optional[str] = Field(
        None,
        description="Storage unit or locker identifier (e.g., L-42, S-10)"
    )
    dimensions: Optional[str] = Field(
        None,
        description="Physical dimensions (e.g., '5x10', '10x10x8')"
    )
    access_code: Optional[str] = Field(
        None,
        description="Access code or combination for the unit"
    )
    is_climate_controlled: Optional[bool] = Field(
        None,
        description="Climate controlled storage"
    )
    has_power: Optional[bool] = Field(
        None,
        description="Whether the unit has electrical outlets"
    )
    is_indoor: Optional[bool] = Field(
        None,
        description="Whether the storage unit is indoor or outdoor"
    )


class StorageUnitDetailsCreate(StorageUnitDetails):
    """Schema for creating storage unit details."""
    pass


class StorageUnitDetailsUpdate(StorageUnitDetails):
    """Schema for updating storage unit details. All fields optional."""
    unit_type: Literal['Locker', 'Storage'] = Field(
        'Storage',
        description="Either 'Locker' for small storage or 'Storage' for larger units"
    )


class StorageUnitDetailsResponse(StorageUnitDetails):
    """Schema for storage unit details in responses."""
    pass


__all__ = [
    'StorageUnitDetails',
    'StorageUnitDetailsCreate',
    'StorageUnitDetailsUpdate',
    'StorageUnitDetailsResponse',
]

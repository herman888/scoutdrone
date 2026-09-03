"""
Generic unit type-specific detail schemas.
For generic units and other types that don't fit specific categories.
"""
from typing import Literal, Optional
from pydantic import Field

from .base import UnitTypeDetailsBase


class OtherUnitDetails(UnitTypeDetailsBase):
    """Base generic unit details with flexible fields."""
    
    unit_type: Literal['Unit', 'Other'] = Field(
        'Unit',
        description="Generic 'Unit' or 'Other' for uncategorized units"
    )
    
    # Generic fields - minimal schema for flexibility
    notes: Optional[str] = Field(
        None,
        description="Additional notes about the unit"
    )


class OtherUnitDetailsCreate(OtherUnitDetails):
    """Schema for creating generic unit details."""
    pass


class OtherUnitDetailsUpdate(OtherUnitDetails):
    """Schema for updating generic unit details. All fields optional."""
    unit_type: Literal['Unit', 'Other'] = Field(
        'Unit',
        description="Generic 'Unit' or 'Other' for uncategorized units"
    )


class OtherUnitDetailsResponse(OtherUnitDetails):
    """Schema for generic unit details in responses."""
    pass


__all__ = [
    'OtherUnitDetails',
    'OtherUnitDetailsCreate',
    'OtherUnitDetailsUpdate',
    'OtherUnitDetailsResponse',
]

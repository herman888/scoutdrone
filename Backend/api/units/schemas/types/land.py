"""
Land unit type-specific detail schemas.
For land parcels and lots.
"""
from typing import Literal, Optional, List
from decimal import Decimal
from pydantic import Field

from .base import UnitTypeDetailsBase


class LandUnitDetails(UnitTypeDetailsBase):
    """Base land unit details with common fields."""
    
    unit_type: Literal['Land'] = 'Land'
    
    # Land-specific fields
    # Note: Land size (acreage) is stored in the main 'size' field of PropertyUnit
    parcel_number: Optional[str] = Field(
        None,
        description="Official parcel identification number"
    )
    zoning: Optional[str] = Field(
        None,
        description="Zoning classification"
    )
    utilities_available: Optional[List[str]] = Field(
        None,
        description="List of available utilities (e.g., ['water', 'electric', 'sewer', 'gas'])"
    )
    has_road_access: Optional[bool] = Field(
        None,
        description="Whether the land has road access"
    )
    is_cleared: Optional[bool] = Field(
        None,
        description="Whether the land is cleared and ready for development"
    )
    topography: Optional[str] = Field(
        None,
        description="Land topography type (e.g., 'flat', 'rolling', 'sloped', 'hilly', 'mixed')"
    )


class LandUnitDetailsCreate(LandUnitDetails):
    """Schema for creating land unit details."""
    pass


class LandUnitDetailsUpdate(LandUnitDetails):
    """Schema for updating land unit details. All fields optional."""
    unit_type: Literal['Land'] = 'Land'


class LandUnitDetailsResponse(LandUnitDetails):
    """Schema for land unit details in responses."""
    pass


__all__ = [
    'LandUnitDetails',
    'LandUnitDetailsCreate',
    'LandUnitDetailsUpdate',
    'LandUnitDetailsResponse',
]

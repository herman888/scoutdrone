"""
Parking unit type-specific detail schemas.
For parking spaces, garages, and vehicle storage units.
"""
from typing import Literal, Optional
from pydantic import Field

from .base import UnitTypeDetailsBase


class ParkingUnitDetails(UnitTypeDetailsBase):
    """Base parking unit details with common fields."""
    
    unit_type: Literal['Parking'] = 'Parking'
    
    # Parking-specific fields
    space_number: Optional[str] = Field(
        None,
        description="Parking space identifier (e.g., P-15, Spot 42)"
    )
    is_covered: Optional[bool] = Field(
        None,
        description="Whether the parking space is covered/indoor"
    )
    is_accessible: Optional[bool] = Field(
        None,
        description="ADA/accessibility compliant parking"
    )
    ev_charging: Optional[bool] = Field(
        None,
        description="Electric vehicle charging available"
    )
    vehicle_type: Optional[str] = Field(
        None,
        description="Type of vehicle allowed (e.g., car, motorcycle, truck, rv, other)"
    )


class ParkingUnitDetailsCreate(ParkingUnitDetails):
    """Schema for creating parking unit details."""
    pass


class ParkingUnitDetailsUpdate(ParkingUnitDetails):
    """Schema for updating parking unit details. All fields optional."""
    unit_type: Literal['Parking'] = 'Parking'


class ParkingUnitDetailsResponse(ParkingUnitDetails):
    """Schema for parking unit details in responses."""
    pass


__all__ = [
    'ParkingUnitDetails',
    'ParkingUnitDetailsCreate',
    'ParkingUnitDetailsUpdate',
    'ParkingUnitDetailsResponse',
]

"""
Unit type-specific detail schemas.

This module provides Pydantic schemas for different unit types, similar to
the property type details pattern. The unit_type field acts as a discriminator
for proper validation and serialization.

Each unit type has its own set of required and optional fields:
- Residential: bedrooms, bathrooms, appliances, parking, etc.
- Industrial: ownership_entity_id, additional_rent, lease_structure, etc.
- Parking: space_number, is_covered, ev_charging, etc.
- Storage/Locker: dimensions, access_code, climate_controlled, etc.
- Land: parcel_number, acreage, zoning, etc.
- Unit/Other: generic flexible fields

The discriminated union allows FastAPI to automatically validate and route
to the correct schema based on the unit_type field.
"""
from typing import Union, Annotated
from pydantic import Field

from .base import UnitTypeDetailsBase
from .residential import (
    ResidentialUnitDetails,
    ResidentialUnitDetailsCreate,
    ResidentialUnitDetailsUpdate,
    ResidentialUnitDetailsResponse
)
from .industrial import (
    IndustrialUnitDetails,
    IndustrialUnitDetailsCreate,
    IndustrialUnitDetailsUpdate,
    IndustrialUnitDetailsResponse
)
from .parking import (
    ParkingUnitDetails,
    ParkingUnitDetailsCreate,
    ParkingUnitDetailsUpdate,
    ParkingUnitDetailsResponse
)
from .storage import (
    StorageUnitDetails,
    StorageUnitDetailsCreate,
    StorageUnitDetailsUpdate,
    StorageUnitDetailsResponse
)
from .land import (
    LandUnitDetails,
    LandUnitDetailsCreate,
    LandUnitDetailsUpdate,
    LandUnitDetailsResponse
)
from .other import (
    OtherUnitDetails,
    OtherUnitDetailsCreate,
    OtherUnitDetailsUpdate,
    OtherUnitDetailsResponse
)

# Discriminated unions for unit type details
# The unit_type field determines which schema to use for validation

UnitTypeDetailsCreate = Annotated[
    Union[
        ResidentialUnitDetailsCreate,
        IndustrialUnitDetailsCreate,
        ParkingUnitDetailsCreate,
        StorageUnitDetailsCreate,
        LandUnitDetailsCreate,
        OtherUnitDetailsCreate
    ],
    Field(discriminator='unit_type')
]

UnitTypeDetailsUpdate = Annotated[
    Union[
        ResidentialUnitDetailsUpdate,
        IndustrialUnitDetailsUpdate,
        ParkingUnitDetailsUpdate,
        StorageUnitDetailsUpdate,
        LandUnitDetailsUpdate,
        OtherUnitDetailsUpdate
    ],
    Field(discriminator='unit_type')
]

UnitTypeDetailsResponse = Annotated[
    Union[
        ResidentialUnitDetailsResponse,
        IndustrialUnitDetailsResponse,
        ParkingUnitDetailsResponse,
        StorageUnitDetailsResponse,
        LandUnitDetailsResponse,
        OtherUnitDetailsResponse
    ],
    Field(discriminator='unit_type')
]

__all__ = [
    # Base
    'UnitTypeDetailsBase',

    # Residential
    'ResidentialUnitDetails',
    'ResidentialUnitDetailsCreate',
    'ResidentialUnitDetailsUpdate',
    'ResidentialUnitDetailsResponse',

    # Industrial
    'IndustrialUnitDetails',
    'IndustrialUnitDetailsCreate',
    'IndustrialUnitDetailsUpdate',
    'IndustrialUnitDetailsResponse',

    # Parking
    'ParkingUnitDetails',
    'ParkingUnitDetailsCreate',
    'ParkingUnitDetailsUpdate',
    'ParkingUnitDetailsResponse',

    # Storage/Locker
    'StorageUnitDetails',
    'StorageUnitDetailsCreate',
    'StorageUnitDetailsUpdate',
    'StorageUnitDetailsResponse',

    # Land
    'LandUnitDetails',
    'LandUnitDetailsCreate',
    'LandUnitDetailsUpdate',
    'LandUnitDetailsResponse',

    # Unit/Other
    'OtherUnitDetails',
    'OtherUnitDetailsCreate',
    'OtherUnitDetailsUpdate',
    'OtherUnitDetailsResponse',

    # Discriminated unions
    'UnitTypeDetailsCreate',
    'UnitTypeDetailsUpdate',
    'UnitTypeDetailsResponse',
]

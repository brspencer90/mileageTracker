"""Pydantic request/response schemas (see docs/IMPLEMENTATION_PLAN.md section 3)."""

import datetime

from pydantic import BaseModel, Field

ZIP_PATTERN = r"^\d{5}$"


class VehicleOut(BaseModel):
    id: int
    name: str
    make: str | None = None
    model: str | None = None
    year: int | None = None
    tank_size_gal: float | None = None


class FillupCreate(BaseModel):
    vehicle_id: int
    date: datetime.date
    # MT-24: mileage is optional. Omitted/null -> a "pending" fill (logged at
    # the pump without an odometer reading); when present it must be > 0.
    mileage: int | None = Field(default=None, gt=0)
    gallons: float = Field(gt=0)
    cost: float = Field(gt=0)
    station: str | None = None
    zip: str | None = Field(default=None, pattern=ZIP_PATTERN)
    missed_last_fill: bool = False


class ResolveMileage(BaseModel):
    """Body for POST /api/fillups/{id}/resolve-mileage (accept the estimate)."""

    mileage: int = Field(gt=0)


class FillupUpdate(BaseModel):
    """PATCH semantics: only fields explicitly provided are applied."""

    date: datetime.date | None = None
    mileage: int | None = Field(default=None, gt=0)
    gallons: float | None = Field(default=None, gt=0)
    cost: float | None = Field(default=None, gt=0)
    station: str | None = None
    zip: str | None = Field(default=None, pattern=ZIP_PATTERN)
    missed_last_fill: bool | None = None


class FillupOut(BaseModel):
    id: int
    vehicle_id: int
    date: datetime.date
    mileage: int | None  # nullable: MT-24 pending fills carry no odometer reading
    gallons: float
    cost: float | None  # nullable: one historical row has no recorded cost
    station: str | None = None
    zip: str | None = None
    missed_last_fill: bool
    mileage_estimated: bool = False  # odometer reconstructed on import (MT-21) or backfill (MT-24)
    gauge_notches: float | None = None  # raw xlsx gauge column (MT-20/MT-22)
    mpf: int | None = None
    mpg: float | None = None
    mpg_estimated: bool = False  # MPG rests on >=1 estimated odometer reading
    # MT-24: for a pending row bracketed by real fills before AND after (by
    # date), the gallons-weighted interpolation estimate; else null.
    suggested_mileage: int | None = None
    created_at: str


class FillupList(BaseModel):
    items: list[FillupOut]
    total: int


class StationPick(BaseModel):
    station: str
    zip: str | None = None


class FillupContext(BaseModel):
    prev_mileage: int | None = None
    last_station: str | None = None
    last_zip: str | None = None
    recent_stations: list[StationPick] = []
    tank_size_gal: float | None = None


class MpgPoint(BaseModel):
    date: datetime.date
    mileage: int
    mpg: float | None = None
    estimated: bool = False  # MPG rests on >=1 estimated odometer reading


class MonthCost(BaseModel):
    month: str  # "2023-11"
    cost: float
    gallons: float
    fillups: int

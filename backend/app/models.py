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


class SummaryStats(BaseModel):
    """Dashboard summary tiles for one vehicle (GET /api/stats/summary).

    The [15,40] MPG band on lifetime/recent averages deliberately drops the
    history's unflagged partial-fill outliers (which derive to 45-57+ MPG) so
    the headline averages aren't skewed; see docs/PRODUCT_PLAN.md / CLAUDE.md.
    """

    odometer: int | None = None  # MAX(mileage); pending (NULL) rows ignored
    total_fills: int  # all rows incl. pending
    tracked_since: datetime.date | None = None  # MIN(date)
    lifetime_mpg: float | None = None  # mean derived mpg in [15,40], 1dp
    recent_mpg: float | None = None  # mean of most recent 8 in-band mpg, 1dp
    mpg_delta: float | None = None  # recent - lifetime, 1dp
    cost_per_mile: float | None = None  # over most recent 10 real fills, 3dp
    spend_30d: float | None = None  # SUM(cost) within 30d of latest fill
    spend_30d_fills: int  # count of fills in that window
    avg_days_between: float | None = None  # mean gap over recent 12 fills, 1dp

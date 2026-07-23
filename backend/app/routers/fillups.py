import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import queries
from ..db import get_db
from ..models import (
    FillupContext,
    FillupCreate,
    FillupList,
    FillupOut,
    FillupUpdate,
    ResolveMileage,
)

router = APIRouter(prefix="/api/fillups", tags=["fillups"])


def _to_out(row: sqlite3.Row, suggested_mileage: int | None = None) -> dict:
    """Derived-query row -> FillupOut payload (money rounded at the API boundary)."""
    d = dict(row)
    return {
        "id": d["id"],
        "vehicle_id": d["vehicle_id"],
        "date": d["date"],
        "mileage": d["mileage"],
        "gallons": d["gallons"],
        "cost": round(d["cost"], 2) if d["cost"] is not None else None,
        "station": d["station"],
        "zip": d["zip"],
        "missed_last_fill": bool(d["missed_last_fill"]),
        "mileage_estimated": bool(d["mileage_estimated"]),
        "gauge_notches": d["gauge_notches"],
        "mpf": d["mpf"],
        "mpg": d["mpg"],
        "mpg_estimated": bool(d["mpg_estimated"]),
        "suggested_mileage": suggested_mileage,
        "created_at": d["created_at"],
    }


def _out_with_suggestion(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    """FillupOut for a single row, computing its backfill suggestion if pending."""
    suggested = None
    if row["mileage"] is None:
        suggested = queries.suggested_mileages(conn, row["vehicle_id"]).get(row["id"])
    return _to_out(row, suggested)


def _get_vehicle_or_404(conn: sqlite3.Connection, vehicle_id: int) -> sqlite3.Row:
    vehicle = queries.get_vehicle(conn, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found.")
    return vehicle


def _check_date_not_future(value: date) -> None:
    if value > date.today():
        raise HTTPException(status_code=422, detail="Date cannot be in the future.")


def _check_gallons_cap(gallons: float, tank_size_gal: float | None) -> None:
    if tank_size_gal is not None and gallons > tank_size_gal * 1.1:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{gallons} gallons exceeds the tank-size sanity cap of "
                f"{tank_size_gal * 1.1:.1f} gal (tank size {tank_size_gal} gal)."
            ),
        )


@router.get("", response_model=FillupList)
def list_fillups(
    vehicle_id: int,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
):
    _get_vehicle_or_404(conn, vehicle_id)
    rows = queries.list_fillups(conn, vehicle_id, limit, offset)
    suggestions = queries.suggested_mileages(conn, vehicle_id)
    return {
        "items": [_to_out(row, suggestions.get(row["id"])) for row in rows],
        "total": queries.count_fillups(conn, vehicle_id),
    }


@router.get("/context", response_model=FillupContext)
def fillup_context(vehicle_id: int, conn: sqlite3.Connection = Depends(get_db)):
    vehicle = _get_vehicle_or_404(conn, vehicle_id)
    context = queries.fillup_context(conn, vehicle_id)
    context["tank_size_gal"] = vehicle["tank_size_gal"]
    return context


@router.post("", response_model=FillupOut, status_code=201)
def create_fillup(payload: FillupCreate, conn: sqlite3.Connection = Depends(get_db)):
    vehicle = _get_vehicle_or_404(conn, payload.vehicle_id)
    _check_date_not_future(payload.date)
    _check_gallons_cap(payload.gallons, vehicle["tank_size_gal"])
    # MT-24: a null mileage is a "pending" fill (logged without an odometer);
    # the strictly-increasing check only applies when a mileage is supplied.
    if payload.mileage is not None:
        current_max = queries.max_mileage(conn, payload.vehicle_id)
        if current_max is not None and payload.mileage <= current_max:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Mileage must be greater than the vehicle's current maximum "
                    f"({current_max})."
                ),
            )
    fillup_id = queries.insert_fillup(
        conn,
        {
            "vehicle_id": payload.vehicle_id,
            "date": payload.date.isoformat(),
            "mileage": payload.mileage,
            "gallons": payload.gallons,
            "cost": payload.cost,
            "station": payload.station,
            "zip": payload.zip,
            "missed_last_fill": 1 if payload.missed_last_fill else 0,
        },
    )
    return _out_with_suggestion(conn, queries.get_fillup(conn, fillup_id))


@router.patch("/{fillup_id}", response_model=FillupOut)
def update_fillup(
    fillup_id: int,
    payload: FillupUpdate,
    conn: sqlite3.Connection = Depends(get_db),
):
    existing = queries.get_fillup_raw(conn, fillup_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Fill-up {fillup_id} not found.")
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return _to_out(queries.get_fillup(conn, fillup_id))

    if "date" in fields and fields["date"] is not None:
        _check_date_not_future(fields["date"])
        fields["date"] = fields["date"].isoformat()
    if "gallons" in fields:
        vehicle = queries.get_vehicle(conn, existing["vehicle_id"])
        _check_gallons_cap(fields["gallons"], vehicle["tank_size_gal"])
    if "mileage" in fields:
        prev, nxt = queries.neighbor_mileages(
            conn, existing["vehicle_id"], fillup_id, existing["mileage"]
        )
        new_mileage = fields["mileage"]
        if (prev is not None and new_mileage <= prev) or (
            nxt is not None and new_mileage >= nxt
        ):
            bounds = f"greater than {prev}" if prev is not None else ""
            if nxt is not None:
                bounds += (" and " if bounds else "") + f"less than {nxt}"
            raise HTTPException(
                status_code=422,
                detail=f"Mileage must stay between its neighbors: {bounds}.",
            )
    if "missed_last_fill" in fields and fields["missed_last_fill"] is not None:
        fields["missed_last_fill"] = 1 if fields["missed_last_fill"] else 0

    queries.update_fillup(conn, fillup_id, fields)
    return _to_out(queries.get_fillup(conn, fillup_id))


@router.post("/{fillup_id}/resolve-mileage", response_model=FillupOut)
def resolve_mileage(
    fillup_id: int,
    payload: ResolveMileage,
    conn: sqlite3.Connection = Depends(get_db),
):
    """MT-24: accept a backfill estimate for a pending fill. Sets mileage to the
    supplied value and mileage_estimated=1; the derived MPG then materializes.
    """
    existing = queries.get_fillup_raw(conn, fillup_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Fill-up {fillup_id} not found.")
    if existing["mileage"] is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Fill-up {fillup_id} already has a mileage; nothing to resolve.",
        )
    prev, nxt = queries.date_neighbor_mileages(
        conn, existing["vehicle_id"], existing["date"]
    )
    if prev is None or nxt is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "This fill is not yet bracketed by real fills before and after "
                "its date, so a mileage cannot be interpolated."
            ),
        )
    value = payload.mileage
    if value <= prev or value >= nxt:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Mileage must be strictly between its date-neighbors "
                f"({prev} and {nxt})."
            ),
        )
    queries.update_fillup(conn, fillup_id, {"mileage": value, "mileage_estimated": 1})
    return _out_with_suggestion(conn, queries.get_fillup(conn, fillup_id))


@router.delete("/{fillup_id}", status_code=204)
def delete_fillup(fillup_id: int, conn: sqlite3.Connection = Depends(get_db)):
    if not queries.delete_fillup(conn, fillup_id):
        raise HTTPException(status_code=404, detail=f"Fill-up {fillup_id} not found.")
    return Response(status_code=204)

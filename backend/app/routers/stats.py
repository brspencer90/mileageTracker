import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import queries
from ..db import get_db
from ..models import MonthCost, MpgPoint

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _check_vehicle(conn: sqlite3.Connection, vehicle_id: int) -> None:
    if queries.get_vehicle(conn, vehicle_id) is None:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found.")


@router.get("/mpg", response_model=list[MpgPoint])
def mpg(vehicle_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """MPG per fill-up, ascending by mileage; nulls included (chart gaps at missed fills)."""
    _check_vehicle(conn, vehicle_id)
    return [dict(row) for row in queries.mpg_points(conn, vehicle_id)]


@router.get("/cost-by-month", response_model=list[MonthCost])
def cost_by_month(vehicle_id: int, conn: sqlite3.Connection = Depends(get_db)):
    _check_vehicle(conn, vehicle_id)
    return [dict(row) for row in queries.cost_by_month(conn, vehicle_id)]

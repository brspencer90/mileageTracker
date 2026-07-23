import sqlite3

from fastapi import APIRouter, Depends

from .. import queries
from ..db import get_db
from ..models import VehicleOut

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
def list_vehicles(conn: sqlite3.Connection = Depends(get_db)):
    return [dict(row) for row in queries.list_vehicles(conn)]

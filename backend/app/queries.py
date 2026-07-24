"""All SQL lives here, including the LAG() derivation CTE.

MPF/MPG are derived at read time, never stored (editing/deleting a row would
otherwise corrupt its neighbor's stored values). The ordering axis is mileage
(the true monotonic axis), not date. MPG = mpf / current row's gallons
(standard full-tank method); `missed_last_fill` nulls the derivation.
"""

import datetime
import sqlite3

# Reused by list, single-get, and stats queries. mpg_estimated means "this
# MPG value rests on at least one estimated odometer reading" — the row's own
# mileage_estimated or the previous row's (the interval's other endpoint).
_DERIVED_CTE = """
WITH ordered AS (
    SELECT f.*,
        LAG(mileage) OVER (PARTITION BY vehicle_id ORDER BY mileage) AS prev_mileage,
        LAG(mileage_estimated) OVER (PARTITION BY vehicle_id ORDER BY mileage)
            AS prev_mileage_estimated
    FROM fillups f
    WHERE vehicle_id = :vehicle_id
      AND mileage IS NOT NULL  -- MT-24: pending rows never enter the LAG ordering
),
derived AS (
    SELECT *,
        CASE WHEN missed_last_fill = 0 AND prev_mileage IS NOT NULL
             THEN mileage - prev_mileage END                                    AS mpf,
        CASE WHEN missed_last_fill = 0 AND prev_mileage IS NOT NULL
             THEN ROUND((mileage - prev_mileage) / gallons, 2) END              AS mpg,
        (mileage_estimated = 1 OR COALESCE(prev_mileage_estimated, 0) = 1)      AS mpg_estimated
    FROM ordered
)
"""

_FILLUP_COLUMNS = (
    "vehicle_id",
    "date",
    "mileage",
    "gallons",
    "cost",
    "station",
    "zip",
    "missed_last_fill",
)


# --- vehicles ---------------------------------------------------------------


def list_vehicles(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM vehicles ORDER BY id").fetchall()


def get_vehicle(conn: sqlite3.Connection, vehicle_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)
    ).fetchone()


# --- fillups ----------------------------------------------------------------


# Pending rows (mileage NULL) don't go through the LAG derivation; they're
# unioned back in with null mpf/mpg. Column list must match `derived`
# (fillups.* + prev_mileage + prev_mileage_estimated + mpf + mpg + mpg_estimated).
_PENDING_CTE = """,
pending AS (
    SELECT f.*,
        NULL AS prev_mileage, NULL AS prev_mileage_estimated,
        NULL AS mpf, NULL AS mpg, 0 AS mpg_estimated
    FROM fillups f
    WHERE vehicle_id = :vehicle_id AND mileage IS NULL
),
combined AS (
    SELECT *, 0 AS is_pending FROM derived
    UNION ALL
    SELECT *, 1 AS is_pending FROM pending
)
"""


def list_fillups(
    conn: sqlite3.Connection, vehicle_id: int, limit: int, offset: int
) -> list[sqlite3.Row]:
    # Pending rows first (newest date first), then real rows by mileage DESC.
    return conn.execute(
        _DERIVED_CTE
        + _PENDING_CTE
        + """
SELECT * FROM combined
ORDER BY is_pending DESC,
         CASE WHEN is_pending = 1 THEN date END DESC,
         mileage DESC,
         id DESC
LIMIT :limit OFFSET :offset
""",
        {"vehicle_id": vehicle_id, "limit": limit, "offset": offset},
    ).fetchall()


def count_fillups(conn: sqlite3.Connection, vehicle_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM fillups WHERE vehicle_id = ?", (vehicle_id,)
    ).fetchone()[0]


def get_fillup(conn: sqlite3.Connection, fillup_id: int) -> sqlite3.Row | None:
    """Fetch one fillup with derived mpf/mpg (derivation runs over its vehicle).

    Returns pending rows (mileage NULL) too, with null mpf/mpg/mpg_estimated.
    """
    return conn.execute(
        """
WITH ordered AS (
    SELECT f.*,
        LAG(mileage) OVER (PARTITION BY vehicle_id ORDER BY mileage) AS prev_mileage,
        LAG(mileage_estimated) OVER (PARTITION BY vehicle_id ORDER BY mileage)
            AS prev_mileage_estimated
    FROM fillups f
    WHERE vehicle_id = (SELECT vehicle_id FROM fillups WHERE id = :id)
      AND mileage IS NOT NULL
),
derived AS (
    SELECT *,
        CASE WHEN missed_last_fill = 0 AND prev_mileage IS NOT NULL
             THEN mileage - prev_mileage END                                    AS mpf,
        CASE WHEN missed_last_fill = 0 AND prev_mileage IS NOT NULL
             THEN ROUND((mileage - prev_mileage) / gallons, 2) END              AS mpg,
        (mileage_estimated = 1 OR COALESCE(prev_mileage_estimated, 0) = 1)      AS mpg_estimated
    FROM ordered
),
pending AS (
    SELECT f.*,
        NULL AS prev_mileage, NULL AS prev_mileage_estimated,
        NULL AS mpf, NULL AS mpg, 0 AS mpg_estimated
    FROM fillups f
    WHERE vehicle_id = (SELECT vehicle_id FROM fillups WHERE id = :id)
      AND mileage IS NULL
),
combined AS (
    SELECT * FROM derived
    UNION ALL
    SELECT * FROM pending
)
SELECT * FROM combined WHERE id = :id
""",
        {"id": fillup_id},
    ).fetchone()


def get_fillup_raw(conn: sqlite3.Connection, fillup_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM fillups WHERE id = ?", (fillup_id,)
    ).fetchone()


def max_mileage(conn: sqlite3.Connection, vehicle_id: int) -> int | None:
    return conn.execute(
        "SELECT MAX(mileage) FROM fillups WHERE vehicle_id = ?", (vehicle_id,)
    ).fetchone()[0]


def neighbor_mileages(
    conn: sqlite3.Connection, vehicle_id: int, exclude_id: int, mileage: int
) -> tuple[int | None, int | None]:
    """Mileages of the rows immediately below and above `mileage`, excluding the row itself."""
    prev = conn.execute(
        "SELECT MAX(mileage) FROM fillups WHERE vehicle_id = ? AND id != ? AND mileage < ?",
        (vehicle_id, exclude_id, mileage),
    ).fetchone()[0]
    nxt = conn.execute(
        "SELECT MIN(mileage) FROM fillups WHERE vehicle_id = ? AND id != ? AND mileage > ?",
        (vehicle_id, exclude_id, mileage),
    ).fetchone()[0]
    return prev, nxt


def date_neighbor_mileages(
    conn: sqlite3.Connection, vehicle_id: int, target_date: str
) -> tuple[int | None, int | None]:
    """Mileages of the nearest REAL fills strictly before/after `target_date`.

    Pending rows (mileage NULL) are ignored. Used to bracket-validate a
    resolved backfill value (MT-24).
    """
    prev = conn.execute(
        "SELECT mileage FROM fillups WHERE vehicle_id = ? AND mileage IS NOT NULL"
        " AND date < ? ORDER BY date DESC, id DESC LIMIT 1",
        (vehicle_id, target_date),
    ).fetchone()
    nxt = conn.execute(
        "SELECT mileage FROM fillups WHERE vehicle_id = ? AND mileage IS NOT NULL"
        " AND date > ? ORDER BY date ASC, id ASC LIMIT 1",
        (vehicle_id, target_date),
    ).fetchone()
    return (prev[0] if prev else None, nxt[0] if nxt else None)


def suggested_mileages(
    conn: sqlite3.Connection, vehicle_id: int
) -> dict[int, int]:
    """MT-24 backfill suggestions: {fillup_id: estimated_mileage} for every
    pending (mileage NULL) row bracketed by real fills before AND after (by
    date). Reuses the importer's gallons-weighted interpolation exactly: a run
    of consecutive pending rows splits the bracket's mileage delta by weights =
    each pending row's gallons + the upper anchor's gallons.
    """
    rows = conn.execute(
        "SELECT id, mileage, gallons FROM fillups"
        " WHERE vehicle_id = ? ORDER BY date, id",
        (vehicle_id,),
    ).fetchall()
    out: dict[int, int] = {}
    n = len(rows)
    j = 0
    while j < n:
        if rows[j]["mileage"] is not None:
            j += 1
            continue
        k = j  # run of consecutive pending rows: rows[j:k]
        while k < n and rows[k]["mileage"] is None:
            k += 1
        before = rows[j - 1] if j > 0 else None
        after = rows[k] if k < n else None
        if (
            before is not None
            and before["mileage"] is not None
            and after is not None
            and after["mileage"] is not None
        ):
            delta = after["mileage"] - before["mileage"]
            run = [rows[m] for m in range(j, k)]
            weights = [r["gallons"] for r in run] + [after["gallons"]]
            total = sum(weights)
            cum = 0.0
            for r, weight in zip(run, weights):
                cum += weight
                out[r["id"]] = round(before["mileage"] + delta * cum / total)
        j = k
    return out


def insert_fillup(conn: sqlite3.Connection, data: dict) -> int:
    cols = ", ".join(_FILLUP_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in _FILLUP_COLUMNS)
    cur = conn.execute(
        f"INSERT INTO fillups ({cols}) VALUES ({placeholders})", data
    )
    conn.commit()
    return cur.lastrowid


def update_fillup(conn: sqlite3.Connection, fillup_id: int, fields: dict) -> None:
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    conn.execute(
        f"UPDATE fillups SET {assignments} WHERE id = :id",
        {**fields, "id": fillup_id},
    )
    conn.commit()


def delete_fillup(conn: sqlite3.Connection, fillup_id: int) -> bool:
    cur = conn.execute("DELETE FROM fillups WHERE id = ?", (fillup_id,))
    conn.commit()
    return cur.rowcount > 0


def fillup_context(conn: sqlite3.Connection, vehicle_id: int) -> dict:
    """Everything the quick-log form needs at load, in one round trip."""
    last = conn.execute(
        "SELECT mileage, station, zip FROM fillups"
        " WHERE vehicle_id = ? AND mileage IS NOT NULL"  # MT-24: skip pending rows
        " ORDER BY mileage DESC LIMIT 1",
        (vehicle_id,),
    ).fetchone()
    recent = conn.execute(
        "SELECT station, zip, MAX(mileage) AS latest FROM fillups"
        " WHERE vehicle_id = ? AND station IS NOT NULL"
        " GROUP BY station, zip ORDER BY latest DESC LIMIT 5",
        (vehicle_id,),
    ).fetchall()
    return {
        "prev_mileage": last["mileage"] if last else None,
        "last_station": last["station"] if last else None,
        "last_zip": last["zip"] if last else None,
        "recent_stations": [
            {"station": r["station"], "zip": r["zip"]} for r in recent
        ],
    }


# --- stats ------------------------------------------------------------------


def mpg_points(conn: sqlite3.Connection, vehicle_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        _DERIVED_CTE
        + "SELECT date, mileage, mpg, mpg_estimated AS estimated FROM derived"
        " ORDER BY mileage ASC",
        {"vehicle_id": vehicle_id},
    ).fetchall()


# Averages ignore the history's unflagged partial-fill outliers, which derive
# to absurd MPG (45-57+). Anything genuinely achievable sits inside this band.
_MPG_BAND = (15.0, 40.0)


def summary_stats(conn: sqlite3.Connection, vehicle_id: int) -> dict:
    """Dashboard summary tiles for one vehicle (see models.SummaryStats).

    Two fetches, then windowed pieces in Python for readability:
      * `real` — derived rows (mileage NOT NULL) via _DERIVED_CTE, mileage-ordered,
        carrying the LAG-derived mpg. Feeds odometer, the MPG averages, cost/mile.
      * `all_rows` — every row incl. pending (mileage NULL), date-ordered.
        Feeds total_fills, tracked_since, spend_30d, avg_days_between.
    Pending rows carry real cost/gallons/date but no mileage, so they count for
    spend/day-gaps/totals but never for MPG or cost-per-mile.
    """
    real = conn.execute(
        _DERIVED_CTE
        + "SELECT mileage, cost, mpg FROM derived ORDER BY mileage ASC",
        {"vehicle_id": vehicle_id},
    ).fetchall()
    all_rows = conn.execute(
        "SELECT date, cost FROM fillups WHERE vehicle_id = ?"
        " ORDER BY date ASC, id ASC",
        (vehicle_id,),
    ).fetchall()

    lo, hi = _MPG_BAND

    def _mean1(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None

    # --- MPG averages (real rows only, in-band) ---
    in_band = [r["mpg"] for r in real if r["mpg"] is not None and lo <= r["mpg"] <= hi]
    lifetime_mpg = _mean1(in_band)
    recent_mpg = _mean1(in_band[-8:])
    mpg_delta = (
        round(recent_mpg - lifetime_mpg, 1)
        if recent_mpg is not None and lifetime_mpg is not None
        else None
    )

    # --- cost per mile over the most recent 10 real fills ---
    # 10 fills => up to 9 intervals; each interval's cost is its *ending* fill.
    cost_per_mile = None
    window = real[-10:]
    if len(window) >= 2:
        miles = window[-1]["mileage"] - window[0]["mileage"]
        if miles > 0:
            spent = sum(r["cost"] for r in window[1:] if r["cost"] is not None)
            cost_per_mile = round(spent / miles, 3)

    # --- 30-day spend window (all rows, relative to the latest fill's date) ---
    spend_30d = None
    spend_30d_fills = 0
    if all_rows:
        latest = datetime.date.fromisoformat(all_rows[-1]["date"])
        cutoff = latest - datetime.timedelta(days=30)
        recent = [
            r for r in all_rows
            if datetime.date.fromisoformat(r["date"]) >= cutoff
        ]
        spend_30d = round(sum(r["cost"] or 0 for r in recent), 2)
        spend_30d_fills = len(recent)

    # --- average days between the most recent 12 fills (all rows, by date) ---
    avg_days_between = None
    recent_dates = [datetime.date.fromisoformat(r["date"]) for r in all_rows[-12:]]
    if len(recent_dates) >= 2:
        avg_days_between = round(
            (recent_dates[-1] - recent_dates[0]).days / (len(recent_dates) - 1), 1
        )

    return {
        "odometer": real[-1]["mileage"] if real else None,
        "total_fills": len(all_rows),
        "tracked_since": all_rows[0]["date"] if all_rows else None,
        "lifetime_mpg": lifetime_mpg,
        "recent_mpg": recent_mpg,
        "mpg_delta": mpg_delta,
        "cost_per_mile": cost_per_mile,
        "spend_30d": spend_30d,
        "spend_30d_fills": spend_30d_fills,
        "avg_days_between": avg_days_between,
    }


def cost_by_month(conn: sqlite3.Connection, vehicle_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
SELECT strftime('%Y-%m', date) AS month,
       ROUND(COALESCE(SUM(cost), 0), 2) AS cost,  -- SUM skips NULL costs; COALESCE guards all-NULL months
       ROUND(SUM(gallons), 3)  AS gallons,
       COUNT(*)                AS fillups
FROM fillups
WHERE vehicle_id = :vehicle_id
GROUP BY strftime('%Y-%m', date)
ORDER BY month ASC
""",
        {"vehicle_id": vehicle_id},
    ).fetchall()

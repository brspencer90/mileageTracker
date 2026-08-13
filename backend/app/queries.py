"""All SQL lives here (T-SQL for Microsoft SQL Server, pyodbc `?` params), plus
the partial-fill-aware MPG derivation (MT-9).

MPF/MPG are derived at read time, never stored (editing/deleting a row would
otherwise corrupt its neighbor's stored values). The ordering axis is mileage
(the true monotonic axis), not date. MPG = window miles / gallons burned over
that window (standard full-tank method).

MT-9: a `partial_fill` is a top-up that didn't fill the tank to full, so it has
no MPG of its own — its gallons roll forward into the NEXT full fill's window.
`missed_last_fill` corrupts the current window (its miles can't be attributed to
the fuel measured). The old LAG() CTE couldn't express roll-up, so derivation is
now a single O(n) Python pass in `_derive`.
"""

import datetime

_FILLUP_COLUMNS = (
    "vehicle_id",
    "date",
    "mileage",
    "gallons",
    "cost",
    "station",
    "zip",
    "missed_last_fill",
    "partial_fill",
    "gauge_notches",
)


# --- pyodbc row helpers -----------------------------------------------------


def _norm(value):
    """DATE/DATETIME2 come back as date/datetime objects; the Python derivation
    and callers expect ISO strings (as SQLite returned). Normalize on read."""
    if isinstance(value, datetime.date):  # also matches datetime.datetime
        return value.isoformat()
    return value


def _rows(cursor) -> list[dict]:
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, (_norm(v) for v in row))) for row in cursor.fetchall()]


def _one(cursor) -> dict | None:
    cols = [c[0] for c in cursor.description]
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip(cols, (_norm(v) for v in row)))


# --- MT-9 derivation --------------------------------------------------------


def _median(values: list[float]) -> float | None:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _derive(rows: list[dict]) -> list[dict]:
    """Partial-fill-aware MPG derivation over one vehicle's real fills.

    `rows` must be that vehicle's fills with mileage NOT NULL, ordered by mileage
    ascending. Returns dicts (copies) with mpf, mpg, mpg_estimated, and
    suggested_partial added.

    Algorithm: walk fills in mileage order, accumulating gallons since the last
    full fill that opened a clean window (`anchor`). A full fill closes the
    window: mpg = (its mileage - anchor) / gallons burned since the anchor. mpf/
    mpg are None for partial fills, the first full fill (no anchor), any full
    fill whose window was corrupted by a missed fill, and leading/trailing
    partials. mpg_estimated for a full fill = this fill's mileage estimated OR the
    anchor's mileage estimated.
    """
    out = [dict(r) for r in rows]

    anchor: int | None = None       # mileage of the last full fill that opened a window
    anchor_estimated = False
    accum = 0.0                     # gallons added since anchor (incl. the closing fill)
    window_valid = True             # no missed-fill gap since anchor

    for row in out:
        if row["missed_last_fill"]:
            window_valid = False
        accum += row["gallons"]
        if not row["partial_fill"]:  # FULL fill: close the window
            if anchor is not None and window_valid and accum > 0:
                row["mpf"] = row["mileage"] - anchor
                row["mpg"] = round(row["mpf"] / accum, 2)
                row["mpg_estimated"] = bool(row["mileage_estimated"] or anchor_estimated)
            else:
                row["mpf"] = None
                row["mpg"] = None
                row["mpg_estimated"] = bool(row["mileage_estimated"])
            anchor = row["mileage"]
            anchor_estimated = bool(row["mileage_estimated"])
            accum = 0.0
            window_valid = True      # open a fresh window here
        else:                        # PARTIAL fill: no MPG, keep accumulating
            row["mpf"] = None
            row["mpg"] = None
            row["mpg_estimated"] = bool(row["mileage_estimated"])

    # --- auto-suggest detector (a hint; flags nothing) ---
    median_full = _median([r["gallons"] for r in out if not r["partial_fill"]])
    for row in out:
        candidate = (
            not row["partial_fill"]
            and not row["missed_last_fill"]
            and row["mileage"] is not None
        )
        high_mpg = row["mpg"] is not None and row["mpg"] > 40
        tiny_fill = median_full is not None and row["gallons"] < 0.55 * median_full
        row["suggested_partial"] = bool(candidate and (high_mpg or tiny_fill))

    return out


def _augment_pending(row: dict) -> dict:
    """A pending row (mileage NULL) carries no derivation."""
    d = dict(row)
    d["mpf"] = None
    d["mpg"] = None
    d["mpg_estimated"] = False
    d["suggested_partial"] = False
    return d


def _real_rows(conn, vehicle_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM fillups WHERE vehicle_id = ? AND mileage IS NOT NULL"
        " ORDER BY mileage ASC, id ASC",
        vehicle_id,
    )
    return _rows(cur)


def _pending_rows(conn, vehicle_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM fillups WHERE vehicle_id = ? AND mileage IS NULL"
        " ORDER BY [date] DESC, id DESC",
        vehicle_id,
    )
    return _rows(cur)


# --- vehicles ---------------------------------------------------------------


def list_vehicles(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM vehicles ORDER BY id")
    return _rows(cur)


def get_vehicle(conn, vehicle_id: int) -> dict | None:
    cur = conn.cursor()
    cur.execute("SELECT * FROM vehicles WHERE id = ?", vehicle_id)
    return _one(cur)


# --- fillups ----------------------------------------------------------------


def list_fillups(conn, vehicle_id: int, limit: int, offset: int) -> list[dict]:
    # Pending rows first (newest date first), then real rows by mileage DESC.
    pending = [_augment_pending(r) for r in _pending_rows(conn, vehicle_id)]
    real_desc = list(reversed(_derive(_real_rows(conn, vehicle_id))))
    combined = pending + real_desc
    return combined[offset : offset + limit]


def count_fillups(conn, vehicle_id: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fillups WHERE vehicle_id = ?", vehicle_id)
    return cur.fetchone()[0]


def get_fillup(conn, fillup_id: int) -> dict | None:
    """Fetch one fillup with derived mpf/mpg (derivation runs over its vehicle).

    Returns pending rows (mileage NULL) too, with null mpf/mpg/mpg_estimated.
    """
    cur = conn.cursor()
    cur.execute("SELECT vehicle_id, mileage FROM fillups WHERE id = ?", fillup_id)
    raw = cur.fetchone()
    if raw is None:
        return None
    vehicle_id, mileage = raw[0], raw[1]
    if mileage is None:
        cur.execute("SELECT * FROM fillups WHERE id = ?", fillup_id)
        return _augment_pending(_one(cur))
    for row in _derive(_real_rows(conn, vehicle_id)):
        if row["id"] == fillup_id:
            return row
    return None


def get_fillup_raw(conn, fillup_id: int) -> dict | None:
    cur = conn.cursor()
    cur.execute("SELECT * FROM fillups WHERE id = ?", fillup_id)
    return _one(cur)


def max_mileage(conn, vehicle_id: int) -> int | None:
    cur = conn.cursor()
    cur.execute("SELECT MAX(mileage) FROM fillups WHERE vehicle_id = ?", vehicle_id)
    return cur.fetchone()[0]


def neighbor_mileages(
    conn, vehicle_id: int, exclude_id: int, mileage: int
) -> tuple[int | None, int | None]:
    """Mileages of the rows immediately below and above `mileage`, excluding the row itself."""
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(mileage) FROM fillups WHERE vehicle_id = ? AND id != ? AND mileage < ?",
        vehicle_id, exclude_id, mileage,
    )
    prev = cur.fetchone()[0]
    cur.execute(
        "SELECT MIN(mileage) FROM fillups WHERE vehicle_id = ? AND id != ? AND mileage > ?",
        vehicle_id, exclude_id, mileage,
    )
    nxt = cur.fetchone()[0]
    return prev, nxt


def date_neighbor_mileages(
    conn, vehicle_id: int, target_date: str
) -> tuple[int | None, int | None]:
    """Mileages of the nearest REAL fills strictly before/after `target_date`.

    Pending rows (mileage NULL) are ignored. Used to bracket-validate a
    resolved backfill value (MT-24).
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT TOP 1 mileage FROM fillups WHERE vehicle_id = ? AND mileage IS NOT NULL"
        " AND [date] < ? ORDER BY [date] DESC, id DESC",
        vehicle_id, target_date,
    )
    prev = cur.fetchone()
    cur.execute(
        "SELECT TOP 1 mileage FROM fillups WHERE vehicle_id = ? AND mileage IS NOT NULL"
        " AND [date] > ? ORDER BY [date] ASC, id ASC",
        vehicle_id, target_date,
    )
    nxt = cur.fetchone()
    return (prev[0] if prev else None, nxt[0] if nxt else None)


def suggested_mileages(conn, vehicle_id: int) -> dict[int, int]:
    """MT-24 backfill suggestions: {fillup_id: estimated_mileage} for every
    pending (mileage NULL) row bracketed by real fills before AND after (by
    date). Reuses the importer's gallons-weighted interpolation exactly: a run
    of consecutive pending rows splits the bracket's mileage delta by weights =
    each pending row's gallons + the upper anchor's gallons.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT id, mileage, gallons FROM fillups"
        " WHERE vehicle_id = ? ORDER BY [date], id",
        vehicle_id,
    )
    rows = _rows(cur)
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


def insert_fillup(conn, data: dict) -> int:
    cols = ", ".join(f"[{c}]" for c in _FILLUP_COLUMNS)
    placeholders = ", ".join("?" for _ in _FILLUP_COLUMNS)
    params = tuple(data[c] for c in _FILLUP_COLUMNS)
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO fillups ({cols}) OUTPUT INSERTED.id VALUES ({placeholders})",
        params,
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    return new_id


def update_fillup(conn, fillup_id: int, fields: dict) -> None:
    assignments = ", ".join(f"[{k}] = ?" for k in fields)
    params = tuple(fields.values()) + (fillup_id,)
    cur = conn.cursor()
    cur.execute(f"UPDATE fillups SET {assignments} WHERE id = ?", params)
    conn.commit()


def delete_fillup(conn, fillup_id: int) -> bool:
    cur = conn.cursor()
    cur.execute("DELETE FROM fillups WHERE id = ?", fillup_id)
    rowcount = cur.rowcount
    conn.commit()
    return rowcount > 0


def fillup_context(conn, vehicle_id: int) -> dict:
    """Everything the quick-log form needs at load, in one round trip."""
    cur = conn.cursor()
    cur.execute(
        "SELECT TOP 1 mileage, station, zip FROM fillups"
        " WHERE vehicle_id = ? AND mileage IS NOT NULL"  # MT-24: skip pending rows
        " ORDER BY mileage DESC",
        vehicle_id,
    )
    last = _one(cur)
    cur.execute(
        "SELECT TOP 5 station, zip, MAX(mileage) AS latest FROM fillups"
        " WHERE vehicle_id = ? AND station IS NOT NULL"
        " GROUP BY station, zip ORDER BY latest DESC",
        vehicle_id,
    )
    recent = _rows(cur)
    return {
        "prev_mileage": last["mileage"] if last else None,
        "last_station": last["station"] if last else None,
        "last_zip": last["zip"] if last else None,
        "recent_stations": [
            {"station": r["station"], "zip": r["zip"]} for r in recent
        ],
    }


# --- stats ------------------------------------------------------------------


def mpg_points(conn, vehicle_id: int) -> list[dict]:
    # Derived real rows ascending; a point's mpg is None where derivation is None
    # (partials and missed-fill gaps included, so the chart line breaks there).
    return [
        {
            "date": r["date"],
            "mileage": r["mileage"],
            "mpg": r["mpg"],
            "estimated": r["mpg_estimated"],
        }
        for r in _derive(_real_rows(conn, vehicle_id))
    ]


# Averages ignore the history's unflagged partial-fill outliers, which derive
# to absurd MPG (45-57+). Anything genuinely achievable sits inside this band.
_MPG_BAND = (15.0, 40.0)


def summary_stats(conn, vehicle_id: int) -> dict:
    """Dashboard summary tiles for one vehicle (see models.SummaryStats).

    Two fetches, then windowed pieces in Python for readability:
      * `real` — derived rows (mileage NOT NULL) via _derive, mileage-ordered,
        carrying the partial-aware mpg. Feeds odometer, MPG averages, cost/mile.
      * `all_rows` — every row incl. pending (mileage NULL), date-ordered.
        Feeds total_fills, tracked_since, spend_30d, avg_days_between.
    Pending rows carry real cost/gallons/date but no mileage, so they count for
    spend/day-gaps/totals but never for MPG or cost-per-mile.
    """
    real = _derive(_real_rows(conn, vehicle_id))
    cur = conn.cursor()
    cur.execute(
        "SELECT [date], cost FROM fillups WHERE vehicle_id = ?"
        " ORDER BY [date] ASC, id ASC",
        vehicle_id,
    )
    all_rows = _rows(cur)

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


def cost_by_month(conn, vehicle_id: int) -> list[dict]:
    """Monthly cost/gallons/fill counts. The month bucketing is done in Python
    (by date.strftime('%Y-%m')) to avoid dialect-specific date-format SQL."""
    cur = conn.cursor()
    cur.execute(
        "SELECT [date], cost, gallons FROM fillups WHERE vehicle_id = ?"
        " ORDER BY [date] ASC, id ASC",
        vehicle_id,
    )
    rows = _rows(cur)
    buckets: dict[str, list] = {}  # month -> [cost_sum, gallons_sum, count]
    for r in rows:
        month = datetime.date.fromisoformat(r["date"]).strftime("%Y-%m")
        b = buckets.setdefault(month, [0.0, 0.0, 0])
        if r["cost"] is not None:  # SUM skips NULL costs
            b[0] += r["cost"]
        b[1] += r["gallons"]
        b[2] += 1
    return [
        {
            "month": month,
            "cost": round(b[0], 2),
            "gallons": round(b[1], 3),
            "fillups": b[2],
        }
        for month, b in sorted(buckets.items())
    ]

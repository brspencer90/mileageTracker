-- MT-24: in-app mileage backfill. A fill can be logged at the pump without an
-- odometer reading and stored "pending" (mileage NULL); a later date-bracketed
-- interpolation offers an estimate the user can accept.
--
-- SQLite can't drop NOT NULL via ALTER, so the table is rebuilt: identical to
-- the post-0002 schema EXCEPT mileage becomes nullable
-- (CHECK (mileage IS NULL OR mileage > 0)). All rows are copied verbatim, the
-- old table dropped, the new one renamed, and the date index recreated. No
-- other table references fillups, so foreign-key integrity is unaffected by the
-- drop/rename (fillups is the child of vehicles, not a parent).
--
-- UNIQUE(vehicle_id, mileage) is kept: SQLite treats NULLs as distinct, so
-- multiple pending rows per vehicle are allowed while real rows stay unique.

CREATE TABLE fillups_new (
    id                INTEGER PRIMARY KEY,
    vehicle_id        INTEGER NOT NULL REFERENCES vehicles(id),
    date              TEXT NOT NULL CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    mileage           INTEGER CHECK (mileage IS NULL OR mileage > 0),  -- nullable (MT-24 pending fills)
    gallons           REAL NOT NULL CHECK (gallons > 0),
    cost              REAL CHECK (cost IS NULL OR cost > 0),  -- nullable: real history has one blank cost
    station           TEXT,                        -- nullable: history has blanks
    zip               TEXT CHECK (zip IS NULL OR zip GLOB '[0-9][0-9][0-9][0-9][0-9]'),
    missed_last_fill  INTEGER NOT NULL DEFAULT 0 CHECK (missed_last_fill IN (0,1)),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    mileage_estimated INTEGER NOT NULL DEFAULT 0 CHECK (mileage_estimated IN (0,1)),
    gauge_notches     REAL,
    UNIQUE (vehicle_id, mileage)                   -- also the importer's idempotency key; NULLs distinct
);

INSERT INTO fillups_new
    (id, vehicle_id, date, mileage, gallons, cost, station, zip,
     missed_last_fill, created_at, mileage_estimated, gauge_notches)
SELECT
    id, vehicle_id, date, mileage, gallons, cost, station, zip,
    missed_last_fill, created_at, mileage_estimated, gauge_notches
FROM fillups;

DROP TABLE fillups;
ALTER TABLE fillups_new RENAME TO fillups;

CREATE INDEX idx_fillups_vehicle_date ON fillups (vehicle_id, date);

PRAGMA user_version = 3;

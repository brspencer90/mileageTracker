CREATE TABLE vehicles (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    make          TEXT,
    model         TEXT,
    year          INTEGER,
    tank_size_gal REAL,                          -- soft cap for gallons validation (legacy hardcoded 13.0)
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE fillups (
    id               INTEGER PRIMARY KEY,
    vehicle_id       INTEGER NOT NULL REFERENCES vehicles(id),
    date             TEXT NOT NULL CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    mileage          INTEGER NOT NULL CHECK (mileage > 0),
    gallons          REAL NOT NULL CHECK (gallons > 0),
    cost             REAL CHECK (cost IS NULL OR cost > 0),  -- nullable: real history has one blank cost
    station          TEXT,                        -- nullable: history has blanks
    zip              TEXT CHECK (zip IS NULL OR zip GLOB '[0-9][0-9][0-9][0-9][0-9]'),
    missed_last_fill INTEGER NOT NULL DEFAULT 0 CHECK (missed_last_fill IN (0,1)),
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (vehicle_id, mileage)                  -- also the importer's idempotency key
);

CREATE INDEX idx_fillups_vehicle_date ON fillups (vehicle_id, date);

PRAGMA user_version = 1;

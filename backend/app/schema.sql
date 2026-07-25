-- v2 schema for Microsoft SQL Server (idempotent; run at app startup).
-- The derivation (MPG/MPF, partial-fill roll-up) is done in Python, so this is
-- just storage. NOTE the filtered unique index below: SQL Server's UNIQUE treats
-- NULLs as equal (one NULL only), but MT-24 pending fills need MANY NULL mileages,
-- so uniqueness is enforced only over non-NULL mileage.

IF OBJECT_ID('dbo.vehicles', 'U') IS NULL
CREATE TABLE dbo.vehicles (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    name          NVARCHAR(100) NOT NULL UNIQUE,
    make          NVARCHAR(100) NULL,
    model         NVARCHAR(100) NULL,
    [year]        INT NULL,
    tank_size_gal FLOAT NULL,
    created_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

IF OBJECT_ID('dbo.fillups', 'U') IS NULL
CREATE TABLE dbo.fillups (
    id                INT IDENTITY(1,1) PRIMARY KEY,
    vehicle_id        INT NOT NULL REFERENCES dbo.vehicles(id),
    [date]            DATE NOT NULL,
    mileage           INT NULL CHECK (mileage IS NULL OR mileage > 0),
    gallons           FLOAT NOT NULL CHECK (gallons > 0),
    cost              FLOAT NULL CHECK (cost IS NULL OR cost > 0),
    station           NVARCHAR(200) NULL,
    zip               NVARCHAR(5) NULL,
    missed_last_fill  BIT NOT NULL DEFAULT 0,
    mileage_estimated BIT NOT NULL DEFAULT 0,
    gauge_notches     FLOAT NULL,
    partial_fill      BIT NOT NULL DEFAULT 0,
    created_at        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

-- Uniqueness over real odometer readings only (pending fills carry NULL mileage).
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_fillups_vehicle_mileage')
CREATE UNIQUE INDEX UX_fillups_vehicle_mileage
    ON dbo.fillups(vehicle_id, mileage) WHERE mileage IS NOT NULL;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_fillups_vehicle_date')
CREATE INDEX IX_fillups_vehicle_date ON dbo.fillups(vehicle_id, [date]);

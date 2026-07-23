-- MT-21: reconstructed odometer readings are flagged, never silent.
-- MT-20: unnamed xlsx column H (fuel-gauge notches, quarter steps 0-4.5) is
--        imported raw for the future MT-22 partial-fill detector.
ALTER TABLE fillups ADD COLUMN mileage_estimated INTEGER NOT NULL DEFAULT 0 CHECK (mileage_estimated IN (0,1));
ALTER TABLE fillups ADD COLUMN gauge_notches REAL;

PRAGMA user_version = 2;

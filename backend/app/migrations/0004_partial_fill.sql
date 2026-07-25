-- MT-9: partial-fill flag. A "partial fill" is a top-up that didn't fill the
-- tank to full. Its MPG can't be computed at that fill; instead its fuel rolls
-- into the NEXT full fill's MPG (see queries._derive). This flags the history's
-- unflagged partial fills that otherwise derive to absurd 45-57+ MPG.
--
-- Simple ADD COLUMN (no table rebuild): the column is nullable-free with a
-- constant DEFAULT, so SQLite backfills every existing row to 0 in place.

ALTER TABLE fillups ADD COLUMN partial_fill INTEGER NOT NULL DEFAULT 0 CHECK (partial_fill IN (0,1));

PRAGMA user_version = 4;

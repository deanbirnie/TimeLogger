-- Run this once the database exists (see 01_create_database.sql), e.g.:
--
--   mysql -u timelogger -p timelogger < sql/02_schema.sql
--
-- Safe to re-run: CREATE TABLE IF NOT EXISTS is a no-op if the table already
-- exists.

USE `timelogger`;

CREATE TABLE IF NOT EXISTS `logged_worklogs` (
    -- SHA-1 hex digest of (jira_issue, started, time_spent_seconds) — see
    -- app/ledger.py:fingerprint(). Acts as the natural, idempotent key: the
    -- same work item always produces the same fingerprint, so INSERT IGNORE
    -- can be used to migrate/re-run safely without creating duplicates.
    `fingerprint` CHAR(40) NOT NULL,

    -- Which fingerprint scheme produced the value above, so rows written by an
    -- older scheme can be found and migrated. See app/ledger.py.
    `fingerprint_version` TINYINT UNSIGNED NOT NULL DEFAULT 1,

    `jira_issue` VARCHAR(64) NOT NULL,

    -- Canonical local wall-clock slot, 'YYYY-MM-DDTHH:MM'. This, not `started`,
    -- is what the fingerprint hashes: it carries no UTC offset, so changing the
    -- configured timezone or the timestamp format cannot change an item's
    -- identity and invalidate the ledger.
    `slot` CHAR(16) NOT NULL DEFAULT '',

    -- Stored as the exact string sent to JIRA's "started" field, not as a
    -- native DATETIME. Until BUGS.md items B2-B4 are fixed, this string can
    -- be malformed (e.g. an unpadded or negative hour), which a DATETIME
    -- column would reject outright. Keeping it as text preserves whatever
    -- was actually logged and keeps this table decoupled from those fixes.
    `started` VARCHAR(64) NOT NULL,

    `time_spent_seconds` INT UNSIGNED NOT NULL,
    `description` TEXT NULL,
    `source_file` VARCHAR(255) NULL,
    `logged_at` DATETIME NOT NULL,

    PRIMARY KEY (`fingerprint`),
    INDEX `idx_jira_issue` (`jira_issue`),
    INDEX `idx_logged_at` (`logged_at`),
    INDEX `idx_slot` (`slot`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

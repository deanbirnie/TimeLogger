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

    `jira_issue` VARCHAR(64) NOT NULL,

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
    INDEX `idx_logged_at` (`logged_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

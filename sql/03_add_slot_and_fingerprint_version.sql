-- Upgrade an existing database created before the timestamp fix (BUGS.md B2-B4).
-- Fresh installs get these columns from 02_schema.sql and can skip this file.
--
-- Run as an admin user (the app user has no ALTER privilege, by design):
--
--   mysql -u root -p timelogger < sql/03_add_slot_and_fingerprint_version.sql
--
-- Then recompute the fingerprints of existing rows:
--
--   uv run scripts/migrate_fingerprints.py
--
-- Existing rows default to fingerprint_version 1 and an empty slot; the
-- migration script fills both in. Safe to re-run: each ADD COLUMN is guarded.

USE `timelogger`;

SET @add_version := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'logged_worklogs'
       AND COLUMN_NAME = 'fingerprint_version') = 0,
    'ALTER TABLE `logged_worklogs` ADD COLUMN `fingerprint_version` TINYINT UNSIGNED NOT NULL DEFAULT 1 AFTER `fingerprint`',
    'DO 0'
);
PREPARE stmt FROM @add_version;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_slot := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'logged_worklogs'
       AND COLUMN_NAME = 'slot') = 0,
    'ALTER TABLE `logged_worklogs` ADD COLUMN `slot` CHAR(16) NOT NULL DEFAULT '''' AFTER `jira_issue`',
    'DO 0'
);
PREPARE stmt FROM @add_slot;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_index := IF(
    (SELECT COUNT(*) FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'logged_worklogs'
       AND INDEX_NAME = 'idx_slot') = 0,
    'ALTER TABLE `logged_worklogs` ADD INDEX `idx_slot` (`slot`)',
    'DO 0'
);
PREPARE stmt FROM @add_index;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

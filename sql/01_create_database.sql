-- Run this once against your MySQL/MariaDB server (as a user with permission to
-- create databases and users), e.g.:
--
--   mysql -u root -p < sql/01_create_database.sql
--
-- Edit the password below before running, then use the same values for
-- DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD in your .env file.

CREATE DATABASE IF NOT EXISTS `timelogger`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'timelogger'@'%' IDENTIFIED BY 'change_this_password';

GRANT SELECT, INSERT, UPDATE ON `timelogger`.* TO 'timelogger'@'%';

FLUSH PRIVILEGES;

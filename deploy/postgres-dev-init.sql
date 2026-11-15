-- Run once, when docker-compose.dev.yml creates its database volume: a second database for the
-- Postgres tests (TEST_DATABASE_URL), which wipe it. Never point those tests at your dev database.
CREATE DATABASE botdesk_test;

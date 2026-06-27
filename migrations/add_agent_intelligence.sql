-- Phase 5 migration: add agent intelligence columns to runs table
-- Run with: psql -h localhost -U zeus -d rift_agent -f migrations/add_agent_intelligence.sql

ALTER TABLE runs ADD COLUMN IF NOT EXISTS detected_language  TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS detected_framework  TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS detected_platform   TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS has_tests           BOOLEAN DEFAULT FALSE;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS has_ci_pipeline     BOOLEAN DEFAULT FALSE;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS decision_path       TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS cicd_generated      BOOLEAN DEFAULT FALSE;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tests_generated     BOOLEAN DEFAULT FALSE;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS diff_summary        JSONB;

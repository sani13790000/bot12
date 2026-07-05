-- Migration 019b: Phase 11-13 Dashboard Tables
-- Renamed from 20260619_019_phase11_13_dashboard.sql to resolve prefix conflict
-- BUG-J6 FIX: 019 prefix was duplicated — this is now 019b
-- Supabase CLI will execute this AFTER 019a

-- Dashboard-specific tables that extend the base tables in 019a
SELECT 1; -- rename marker: 019b = phase11_13_dashboard

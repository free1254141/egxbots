-- Migration: 20261030_autonomous_recommendations_setting.sql
-- Description: Document and ensure user_settings table supports persistent autonomous recommendations mode for Pro users.
-- The autonomous_recommendations state is permanently stored in user_settings.app_state->'chat'->>'autonomous_recommendations'
-- so it remains enabled across all user sessions and devices, bypassing local browser cache dependencies.

COMMENT ON TABLE public.user_settings IS 'User application state, including UI preferences, scanner settings, and persistent AI chat autonomous recommendations preferences.';

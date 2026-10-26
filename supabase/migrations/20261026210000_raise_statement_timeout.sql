-- Raise PostgREST / service_role statement timeout to avoid 57014 on analytical scans
-- authenticator is the role used by PostgREST to connect
-- service_role is used for administrative / daily pipeline operations
ALTER ROLE service_role SET statement_timeout = '120s';
ALTER ROLE authenticator SET statement_timeout = '60s';
ALTER ROLE authenticator SET lock_timeout = '30s';

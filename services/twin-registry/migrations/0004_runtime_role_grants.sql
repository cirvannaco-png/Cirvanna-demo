-- Non-login privilege group for the Twin Registry runtime.
-- Create a separate LOGIN role at deployment time and grant it membership here;
-- never place a database password in source control.
CREATE ROLE twin_registry_service NOLOGIN;
REVOKE ALL ON SCHEMA twin_private FROM PUBLIC;
GRANT USAGE ON SCHEMA twin_private TO twin_registry_service;
REVOKE ALL ON ALL TABLES IN SCHEMA twin_private FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA twin_private TO twin_registry_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA twin_private
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA twin_private
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO twin_registry_service;

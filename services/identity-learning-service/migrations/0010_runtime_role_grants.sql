-- Non-login privilege group for the Identity Learning runtime.
-- Create a separate LOGIN role at deployment time and grant it membership here;
-- never place a database password in source control.
CREATE ROLE identity_learning_service NOLOGIN;
REVOKE ALL ON SCHEMA identity_private FROM PUBLIC;
GRANT USAGE ON SCHEMA identity_private TO identity_learning_service;
REVOKE ALL ON ALL TABLES IN SCHEMA identity_private FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity_private TO identity_learning_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA identity_private
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA identity_private
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO identity_learning_service;

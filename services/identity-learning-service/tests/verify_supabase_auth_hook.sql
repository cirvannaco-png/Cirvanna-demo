-- Exercise the private Supabase Auth hook as the only role granted EXECUTE.
SET ROLE supabase_auth_admin;

DO $$
DECLARE
  payload jsonb;
BEGIN
  payload := identity_private.custom_access_token_hook(
    '{"claims":{"role":"authenticated","app_metadata":{"app_role":"merchant"}}}'::jsonb
  );
  IF payload #>> '{claims,app_role}' <> 'merchant'
     OR payload #>> '{claims,role}' <> 'authenticated' THEN
    RAISE EXCEPTION 'Supabase app_role claim mapping failed';
  END IF;

  payload := identity_private.custom_access_token_hook(
    '{"claims":{"role":"authenticated"}}'::jsonb
  );
  IF payload #>> '{claims,app_role}' <> 'customer' THEN
    RAISE EXCEPTION 'default customer role mapping failed';
  END IF;

  payload := identity_private.custom_access_token_hook(
    '{"claims":{"role":"authenticated","app_metadata":{"app_role":"root"}}}'::jsonb
  );
  IF payload #>> '{error,http_code}' <> '403' THEN
    RAISE EXCEPTION 'invalid app_role was not rejected';
  END IF;
END
$$;

RESET ROLE;

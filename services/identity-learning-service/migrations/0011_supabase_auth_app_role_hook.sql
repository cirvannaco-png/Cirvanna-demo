-- Supabase Auth custom access-token hook.
-- app_metadata is server-controlled; user_metadata is deliberately ignored.
-- The built-in JWT "role" remains "authenticated" for Supabase Postgres authorization.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'supabase_auth_admin') THEN
    EXECUTE 'CREATE ROLE supabase_auth_admin NOLOGIN';
  END IF;
END
$$;

GRANT USAGE ON SCHEMA identity_private TO supabase_auth_admin;

CREATE OR REPLACE FUNCTION identity_private.custom_access_token_hook(event jsonb)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
  claims jsonb := event -> 'claims';
  app_role text;
BEGIN
  IF pg_catalog.jsonb_typeof(claims) IS DISTINCT FROM 'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'error',
      pg_catalog.jsonb_build_object('http_code', 500, 'message', 'Missing access-token claims')
    );
  END IF;

  app_role := claims #>> '{app_metadata,app_role}';
  IF app_role IS NULL OR pg_catalog.btrim(app_role) = '' THEN
    app_role := 'customer';
  END IF;

  IF app_role NOT IN ('customer', 'merchant', 'admin') THEN
    RETURN pg_catalog.jsonb_build_object(
      'error',
      pg_catalog.jsonb_build_object('http_code', 403, 'message', 'Invalid Cirvanna application role')
    );
  END IF;

  claims := pg_catalog.jsonb_set(claims, ARRAY['app_role'], pg_catalog.to_jsonb(app_role), true);
  RETURN pg_catalog.jsonb_build_object('claims', claims);
END;
$function$;

REVOKE ALL ON FUNCTION identity_private.custom_access_token_hook(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity_private.custom_access_token_hook(jsonb) TO supabase_auth_admin;

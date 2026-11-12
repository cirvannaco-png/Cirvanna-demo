"""Enforce immutability for CAL purchase authorization evidence.

Revision ID: 20261112_0011
Revises: 20261110_0010
"""
from alembic import op

revision = "20261112_0011"
down_revision = "20261110_0010"
branch_labels = None
depends_on = None

TABLE = "commerce_cal_purchase_audits"
FUNCTION = "commerce_cal_purchase_audits_reject_mutation"
ROW_TRIGGER = "trg_commerce_cal_purchase_audits_no_update_delete"
TRUNCATE_TRIGGER = "trg_commerce_cal_purchase_audits_no_truncate"

POSTGRES_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'commerce_cal_purchase_audits is immutable'
        USING ERRCODE = '55000';
    RETURN NULL;
END;
$$;
"""


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(POSTGRES_FUNCTION)
        op.execute(
            f"""
            CREATE TRIGGER {ROW_TRIGGER}
            BEFORE UPDATE OR DELETE ON {TABLE}
            FOR EACH ROW
            EXECUTE FUNCTION {FUNCTION}()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {TRUNCATE_TRIGGER}
            BEFORE TRUNCATE ON {TABLE}
            FOR EACH STATEMENT
            EXECUTE FUNCTION {FUNCTION}()
            """
        )
    elif dialect == "sqlite":
        op.execute(
            f"""
            CREATE TRIGGER {ROW_TRIGGER}
            BEFORE UPDATE ON {TABLE}
            BEGIN
                SELECT RAISE(ABORT, 'commerce_cal_purchase_audits is immutable');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {ROW_TRIGGER}_delete
            BEFORE DELETE ON {TABLE}
            BEGIN
                SELECT RAISE(ABORT, 'commerce_cal_purchase_audits is immutable');
            END
            """
        )
    else:
        raise RuntimeError(
            f"Unsupported database dialect for CAL audit immutability: {dialect}"
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {TRUNCATE_TRIGGER} ON {TABLE}")
        op.execute(f"DROP TRIGGER IF EXISTS {ROW_TRIGGER} ON {TABLE}")
        op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}()")
    elif dialect == "sqlite":
        op.execute(f"DROP TRIGGER IF EXISTS {ROW_TRIGGER}_delete")
        op.execute(f"DROP TRIGGER IF EXISTS {ROW_TRIGGER}")
    else:
        raise RuntimeError(
            f"Unsupported database dialect for CAL audit immutability: {dialect}"
        )

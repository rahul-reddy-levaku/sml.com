from django.db import migrations

def prep_branch(apps, schema_editor):
    # Work inside Django's atomic block. No manual commits.
    with schema_editor.connection.cursor() as cur:
        # Ensure text column 'branch' exists on companies_staff
        cur.execute("PRAGMA table_info('companies_staff')")
        cols = {row[1] for row in cur.fetchall()}
        if 'branch' not in cols:
            cur.execute("ALTER TABLE companies_staff ADD COLUMN branch varchar(50) NULL")

        # Copy Branch.code from legacy FK (branch_id) when possible
        if 'branch_id' in cols:
            cur.execute("""
                UPDATE companies_staff
                   SET branch = (
                       SELECT b.code
                         FROM companies_branch b
                        WHERE b.id = companies_staff.branch_id
                   )
                 WHERE branch_id IS NOT NULL
                   AND (branch IS NULL OR TRIM(branch) = '' OR LOWER(TRIM(branch)) IN ('branch_id','null','none'))
            """)

        # Normalize/trim
        cur.execute("UPDATE companies_staff SET branch = TRIM(branch) WHERE branch IS NOT NULL")

        # Null-out obviously junk values
        cur.execute("""
            UPDATE companies_staff
               SET branch = NULL
             WHERE branch IS NULL
                OR TRIM(branch) = ''
                OR LOWER(TRIM(branch)) IN ('branch_id','null','none')
        """)

        # Remove values that don't match an existing Branch.code
        cur.execute("""
            UPDATE companies_staff
               SET branch = NULL
             WHERE branch IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM companies_branch b WHERE b.code = companies_staff.branch
               )
        """)

def noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(prep_branch, reverse_code=noop),
    ]

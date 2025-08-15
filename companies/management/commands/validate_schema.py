from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connection
import re
from collections import defaultdict

def normalize(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"[^0-9a-zA-Z]", "", name).strip().lower()

class Command(BaseCommand):
    help = "Validate and optionally sync Django models and database schema for the companies app."

    def add_arguments(self, parser):
        parser.add_argument("--apply-missing-columns", action="store_true", help="Add missing nullable columns to existing tables.")
        parser.add_argument("--auto-rename", action="store_true", help="Automatically rename existing tables whose normalized name matches expected missing tables.")
        parser.add_argument("--fail-on-mismatch", action="store_true", help="Return non-zero if any mismatch remains after fixes.")
        parser.add_argument("--app", default="companies", help="App label to validate (default companies)")

    def handle(self, *args, **options):
        app_label = options["app"]
        apply_cols = options["apply_missing_columns"]
        auto_rename = options["auto_rename"]
        fail_on_mismatch = options["fail_on_mismatch"]

        # 1. check migrations pending using MigrationExecutor
        self.stdout.write("Checking for unapplied migrations...")
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        if plan:
            self.stdout.write(self.style.ERROR("There are unapplied migrations. Run `makemigrations` and `migrate` first."))
        else:
            self.stdout.write(self.style.SUCCESS("No unapplied migrations detected."))

        # 2. Determine expected and existing tables
        app_config = apps.get_app_config(app_label)
        expected_tables = {m._meta.db_table: m for m in app_config.get_models()}
        with connection.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema=%s",
                [connection.settings_dict["NAME"]],
            )
            existing_tables = {row[0] for row in cur.fetchall()}

        missing_tables = set(expected_tables) - existing_tables
        extra_tables = existing_tables - set(expected_tables)

        self.stdout.write("")
        if missing_tables:
            self.stdout.write(self.style.WARNING(f"Missing tables (models exist but DB missing): {sorted(missing_tables)}"))
        else:
            self.stdout.write(self.style.SUCCESS("No missing tables."))

        if extra_tables:
            self.stdout.write(self.style.WARNING(f"Extra tables in DB with no matching model: {sorted(extra_tables)}"))
        else:
            self.stdout.write(self.style.SUCCESS("No extra tables."))

        # 3. Detect near-match renames (normalized)
        norm_expected = {normalize(t): t for t in expected_tables}
        norm_existing = defaultdict(list)
        for t in existing_tables:
            norm_existing[normalize(t)].append(t)

        possible_renames = {}
        for norm, exp_table in norm_expected.items():
            if exp_table in existing_tables:
                continue
            if norm in norm_existing and norm_existing[norm]:
                candidates = norm_existing[norm]
                for cand in candidates:
                    if cand not in expected_tables:
                        possible_renames[cand] = exp_table

        if possible_renames:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Detected possible table renames based on normalized names:"))
            for old, new in possible_renames.items():
                self.stdout.write(f"  {old} -> {new}")
            if auto_rename:
                self.stdout.write("Applying auto-renames...")
                with connection.cursor() as cur:
                    for old, new in possible_renames.items():
                        try:
                            cur.execute(f"RENAME TABLE `{old}` TO `{new}`;")
                            self.stdout.write(self.style.SUCCESS(f"Renamed {old} -> {new}"))
                            missing_tables.discard(new)
                            extra_tables.discard(old)
                            existing_tables.discard(old)
                            existing_tables.add(new)
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"Failed to rename {old} -> {new}: {e}"))

        # 4. Add missing columns to existing tables if requested
        def get_expected_columns(model):
            from django.db import models as mfields
            cols = {}
            for field in model._meta.get_fields():
                if getattr(field, "auto_created", False) and not field.concrete:
                    continue
                if field.many_to_many or field.one_to_many:
                    continue
                colname = field.column
                if colname is None:
                    continue
                if isinstance(field, mfields.CharField):
                    typ = f"VARCHAR({field.max_length})"
                elif isinstance(field, mfields.TextField):
                    typ = "LONGTEXT"
                elif isinstance(field, mfields.FloatField):
                    typ = "DOUBLE"
                elif isinstance(field, mfields.IntegerField):
                    typ = "INT"
                elif isinstance(field, mfields.BigIntegerField):
                    typ = "BIGINT"
                elif isinstance(field, mfields.BooleanField):
                    typ = "TINYINT(1)"
                elif isinstance(field, mfields.JSONField):
                    typ = "JSON"
                elif isinstance(field, mfields.DateField):
                    typ = "DATE"
                elif isinstance(field, mfields.DateTimeField):
                    typ = "DATETIME"
                else:
                    typ = "VARCHAR(255)"
                null_sql = "NULL" if getattr(field, "null", True) else "NOT NULL"
                cols[colname] = f"{typ} {null_sql}"
            return cols

        changed = False
        for table, model in expected_tables.items():
            if table not in existing_tables:
                continue
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
                    [connection.settings_dict["NAME"], table],
                )
                existing_cols = {r[0] for r in cur.fetchall()}
            expected_cols = get_expected_columns(model)
            missing_cols = [c for c in expected_cols if c not in existing_cols]
            if missing_cols:
                self.stdout.write("")
                self.stdout.write(self.style.WARNING(f"Table `{table}` missing columns: {missing_cols}"))
                if apply_cols:
                    with connection.cursor() as cur:
                        for col in missing_cols:
                            definition = expected_cols[col]
                            stmt = f"ALTER TABLE `{table}` ADD COLUMN `{col}` {definition};"
                            try:
                                cur.execute(stmt)
                                self.stdout.write(self.style.SUCCESS(f"  Added column `{col}` to `{table}`"))
                                changed = True
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f"  Failed to add `{col}` to `{table}`: {e}"))

        # 5. Detect ambiguous/similar model names (e.g., Group vs Groups)
        name_map = defaultdict(list)
        for model in app_config.get_models():
            norm = normalize(model.__name__)
            name_map[norm].append(model.__name__)
        ambiguous = {k: v for k, v in name_map.items() if len(v) > 1}
        if ambiguous:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Ambiguous model names (normalized collision); consider renaming or using db_table to disambiguate:"))
            for norm, models in ambiguous.items():
                self.stdout.write(f"  {models} (normalized '{norm}')")

        # Summary
        self.stdout.write("")
        if missing_tables or extra_tables:
            self.stdout.write(self.style.ERROR(f"Remaining missing tables: {sorted(missing_tables)}"))
            self.stdout.write(self.style.ERROR(f"Remaining extra tables: {sorted(extra_tables)}"))
        else:
            self.stdout.write(self.style.SUCCESS("Table-level sync: expected vs existing tables are aligned."))

        if fail_on_mismatch and (missing_tables or extra_tables or changed):
            raise SystemExit(1)

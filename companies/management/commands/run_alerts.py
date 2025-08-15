from django.core.management.base import BaseCommand
from django.conf import settings
from django.apps import apps
from django.utils import timezone
from companies.models import AlertRule, AlertEvent
import json

class Command(BaseCommand):
    help = "Evaluate AlertRule and enqueue/send alerts (feature-flag safe)."

    def handle(self, *args, **options):
        flags = getattr(settings, "SML_FEATURES", {})
        if not flags.get("ESCALATION_ALERTS", False):
            self.stdout.write("ESCALATION_ALERTS OFF")
            return

        qs = AlertRule.objects.filter(is_active=True)
        for rule in qs:
            try:
                entity = (rule.entity or "").lower()
                Model = apps.get_model("companies", entity) or None
                if Model is None:
                    AlertEvent.objects.create(rule_name=rule.name, entity=entity, object_pk="-", status="skipped", message="Unknown entity")
                    continue

                cond = rule.condition or {}
                flt = cond.get("filter", {})
                for obj in Model.objects.filter(**flt)[:5000]:
                    pk = str(getattr(obj, "pk", ""))
                    AlertEvent.objects.create(
                        rule_name=rule.name,
                        entity=entity,
                        object_pk=pk,
                        payload={"snapshot": _safe_model_dict(obj)},
                        status="queued",
                    )
            except Exception as e:
                AlertEvent.objects.create(rule_name=rule.name, entity=rule.entity, object_pk="-", status="failed", message=str(e))

        self.stdout.write("Alerts evaluation complete.")

def _safe_model_dict(obj):
    data = {}
    for f in obj._meta.concrete_fields:
        try:
            data[f.name] = getattr(obj, f.name)
        except Exception:
            data[f.name] = None
    return data

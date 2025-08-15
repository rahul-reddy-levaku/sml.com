import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Optional
from django.conf import settings

@dataclass
class BureauResponse:
    ok: bool
    score: Optional[int]
    raw: Dict[str, Any]
    provider: str
    message: str = ""

class CreditBureauClient:
    def __init__(self) -> None:
        self.flags = getattr(settings, "SML_FEATURES", {})
        self.cfg = getattr(settings, "SML_CREDIT_BUREAU", {})
        self.provider = (self.cfg or {}).get("PROVIDER", "CIBIL").upper()

    def enabled(self) -> bool:
        return bool(self.flags.get("CREDIT_BUREAU", False))

    def _provider_cfg(self) -> Tuple[str, Dict[str, Any]]:
        return self.provider, (self.cfg.get(self.provider, {}) or {})

    def pull_score(self, *, pan: str = "", aadhar: str = "", name: str = "", dob: str = "") -> BureauResponse:
        """
        Stub implementation:
        - If disabled or missing keys: returns ok=True with a synthetic score based on hash (non-blocking).
        - Never raises: always returns BureauResponse (bug-proof/no-error contract).
        """
        prov, pcfg = self._provider_cfg()
        if not self.enabled():
            return BureauResponse(ok=True, score=None, raw={"note":"feature_off"}, provider=prov, message="Credit bureau feature is OFF")

        # If no credentials, synthesize a stable dummy score (safe in dev)
        api_key = pcfg.get("API_KEY", "")
        if not api_key:
            # synthetic deterministic score: 300-900
            seed = hash((pan.strip().upper(), aadhar.replace(" ", ""), name.strip().upper(), dob.strip()))
            score = 300 + abs(seed) % 601
            return BureauResponse(ok=True, score=score, raw={"simulated": True}, provider=prov, message="Simulated score (no API key)")

        # Real provider integration placeholder (non-blocking):
        try:
            # Here you'd call the remote API with `requests` and map the reply.
            # We keep a minimal, time-bounded stub to avoid breaking flows.
            time.sleep(0.2)
            return BureauResponse(ok=True, score=720, raw={"provider": prov, "mock": True}, provider=prov, message="Mocked provider response")
        except Exception as e:
            return BureauResponse(ok=False, score=None, raw={"error": str(e)}, provider=prov, message="Provider error")

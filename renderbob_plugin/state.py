from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PluginState:
  bootstrapped: bool = False
  setup_launched: bool = False
  awaiting_stripe_checkout: bool = False
  auth_ok: bool = False
  status_message: str = "Not authenticated"
  user_email: Optional[str] = None
  credits_eur: Optional[str] = None
  active_job_public_id: Optional[str] = None
  active_job_status: Optional[str] = None
  upload_progress: float = 0.0
  # idle | uploading | estimating — drives Render Setup progress UI during Upload and Estimate
  upload_estimate_stage: str = "idle"
  output_files: List[str] = field(default_factory=list)
  last_error: Optional[str] = None
  diagnostics: Dict[str, Any] = field(default_factory=dict)
  # Last GET /jobs/:id snapshot for panel gating (updated by background poll).
  job_snapshot: Dict[str, Any] = field(default_factory=dict)
  estimate_line1: str = ""
  estimate_line2: str = ""
  log_status_line: str = ""


STATE = PluginState()

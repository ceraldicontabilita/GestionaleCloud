"""Contratti tipizzati del motore decisionale supervisionato."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TipoSegnalazione(str, Enum):
    INFO = "info"
    AVVISO = "avviso"
    URGENTE = "urgente"
    ANOMALIA = "anomalia"
    SUGGERIMENTO = "suggerimento"


class LivelloAutonomia(str, Enum):
    L0 = "L0"  # osservazione
    L1 = "L1"  # raccomandazione
    L2 = "L2"  # esecuzione limitata, solo se la policy la consente
    L3 = "L3"  # approvazione umana obbligatoria
    L4 = "L4"  # azione vietata


class LivelloRischio(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Reversibilita(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class StatoEsecuzione(str, Enum):
    OBSERVED = "observed"
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    READY_L2 = "ready_l2"
    APPROVED_PENDING_EXECUTION = "approved_pending_execution"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"


class DecisioneInput(BaseModel):
    agent: str = Field(min_length=1, max_length=80)
    objective: str = Field(min_length=1, max_length=500)
    input_sources: List[Any] = Field(default_factory=list)
    facts: List[Any] = Field(default_factory=list)
    assumptions: List[Any] = Field(default_factory=list)
    rule_ids: List[str] = Field(default_factory=list)
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_action: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    financial_impact: float = 0.0
    risk_level: LivelloRischio = LivelloRischio.LOW
    reversibility: Reversibilita = Reversibilita.FULL
    autonomy_level: LivelloAutonomia = LivelloAutonomia.L1
    approver_role: str = "admin"
    explanation: str = ""
    rollback_reference: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

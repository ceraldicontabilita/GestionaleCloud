"""Fotografia contabile minimizzata per l'agente Contabile shadow.

Il servizio legge soltanto l'ultimo report del collaudo canonico. Non esegue
nuovi controlli, non genera alert e non modifica collection di business.
Esempi, descrizioni libere e dati identificativi non escono mai dal servizio.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


CRITICAL_CHECKS = frozenset({
    "fatture_banca_senza_estratto_conto",
    "banca_ec_dangling_o_duplicati",
    "fatture_pagate_con_movimento_cancellato",
    "salari_riconciliati_senza_bonifico",
    "movimenti_prima_nota_malformati",
    "trasferimento_pos_speculare",
})


@dataclass(frozen=True)
class ControlloContabile:
    nome: str
    violazioni: int
    critico: bool


@dataclass(frozen=True)
class ContabileSnapshot:
    disponibile: bool
    report_id: Optional[str]
    eseguito_at: Optional[str]
    eta_ore: Optional[float]
    obsoleto: bool
    checks_totali: int
    checks_violati: int
    checks_in_errore: int
    violazioni_totali: int
    violazioni_critiche: int
    controlli: List[ControlloContabile]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _data_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        data = value
    elif value:
        try:
            data = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    return data.astimezone(timezone.utc)


async def leggi_snapshot_contabile(
    db,
    reference_time: Optional[datetime] = None,
    stale_after_hours: int = 30,
) -> ContabileSnapshot:
    """Restituisce solo conteggi e nomi canonici dell'ultimo collaudo."""
    docs = await db["collaudo_report"].find(
        {},
        {
            "_id": 0,
            "id": 1,
            "eseguito_at": 1,
            "checks.nome": 1,
            "checks.violazioni": 1,
        },
    ).sort("eseguito_at", -1).limit(1).to_list(1)
    if not docs:
        return ContabileSnapshot(False, None, None, None, True, 0, 0, 0, 0, 0, [])

    report = docs[0]
    controlli: List[ControlloContabile] = []
    for raw in report.get("checks") or []:
        nome = str(raw.get("nome") or "controllo_senza_nome")[:120]
        try:
            violazioni = int(raw.get("violazioni", -1))
        except (TypeError, ValueError):
            violazioni = -1
        controlli.append(ControlloContabile(
            nome=nome,
            violazioni=violazioni,
            critico=nome in CRITICAL_CHECKS,
        ))

    ora = reference_time or datetime.now(timezone.utc)
    if ora.tzinfo is None:
        ora = ora.replace(tzinfo=timezone.utc)
    eseguito = _data_utc(report.get("eseguito_at"))
    eta_ore = None if not eseguito else max(0.0, (ora - eseguito).total_seconds() / 3600)
    checks_in_errore = sum(1 for item in controlli if item.violazioni < 0)
    violati = [item for item in controlli if item.violazioni > 0]
    return ContabileSnapshot(
        disponibile=True,
        report_id=str(report.get("id") or "report-senza-id")[:120],
        eseguito_at=eseguito.isoformat() if eseguito else None,
        eta_ore=round(eta_ore, 2) if eta_ore is not None else None,
        obsoleto=eta_ore is None or eta_ore > stale_after_hours,
        checks_totali=len(controlli),
        checks_violati=len(violati),
        checks_in_errore=checks_in_errore,
        violazioni_totali=sum(item.violazioni for item in violati),
        violazioni_critiche=sum(
            item.violazioni for item in violati if item.critico
        ),
        controlli=controlli,
    )

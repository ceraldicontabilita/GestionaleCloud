"""SumUp — secondo circuito POS accanto a Nexi/Numia.

Espone la verifica della configurazione (la chiave non viene mai restituita
in chiaro) e la sincronizzazione delle transazioni, che aggiorna la chiusura
giornaliera del circuito SumUp passando dal motore unico di scrittura.
"""
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException

from app.config import settings
from app.database import Database
from app.services import sumup_sync
from app.utils.dependencies import get_current_admin_user, get_current_user
from app.utils.error_handler import handle_errors

router = APIRouter()

TIMEOUT = 20.0
# Recupero prudente: SumUp puo' consolidare una transazione con qualche ora di
# ritardo, quindi la sincronizzazione automatica rilegge anche il giorno prima.
GIORNI_RECUPERO = 7


VARIABILI = ("SUMUP_API_KEY", "SUMUP_MERCHANT_CODE")


def _mascherata(chiave: str) -> str:
    """Ultime 4 cifre soltanto: serve a riconoscerla, non a riusarla."""
    chiave = (chiave or "").strip()
    return f"...{chiave[-4:]}" if len(chiave) >= 4 else ""


def _nomi_nel_file_env(percorso: Path) -> list:
    """Quali delle nostre variabili compaiono nel file .env. Solo i NOMI.

    Il contenuto non viene mai letto in uscita: serve sapere se il file
    definisce la variabile, non quanto vale.
    """
    try:
        righe = percorso.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    presenti = []
    for riga in righe:
        pulita = riga.strip().lstrip("export ").strip()
        for nome in VARIABILI:
            if pulita.startswith(f"{nome}=") and nome not in presenti:
                presenti.append(nome)
    return presenti


def _diagnostica_ambiente(chiave: str, merchant: str) -> Dict[str, Any]:
    """Dove il backend ha trovato — o non ha trovato — le due variabili.

    Distingue i due errori che in pagina danno lo stesso identico sintomo:
    le variabili messe su un altro servizio (qui non arrivano proprio) e le
    variabili presenti ma coperte dal file .env, che in questa applicazione
    ha la precedenza sull'ambiente (vedi settings_customise_sources).
    """
    percorso = Path(str(settings.model_config.get("env_file") or ""))
    esiste = bool(str(percorso)) and percorso.is_file()
    nel_file = _nomi_nel_file_env(percorso) if esiste else []
    nell_ambiente = [n for n in VARIABILI if (os.environ.get(n) or "").strip()]
    caricate = [n for n, v in zip(VARIABILI, (chiave, merchant)) if v]

    diagnostica: Dict[str, Any] = {
        "variabili_nell_ambiente": nell_ambiente,
        "variabili_caricate": caricate,
        "file_env": str(percorso) if esiste else "",
        "file_env_definisce": nel_file,
        "causa_probabile": "",
    }

    coperte = [n for n in nell_ambiente if n in nel_file and n not in caricate]
    if coperte:
        diagnostica["causa_probabile"] = (
            f"Le variabili {', '.join(coperte)} esistono nell'ambiente ma sono "
            f"coperte dal file {percorso}, che ha la precedenza. Rimuovile dal "
            f"file oppure correggile lì."
        )
    elif not chiave and "SUMUP_API_KEY" not in nell_ambiente:
        diagnostica["causa_probabile"] = (
            "SUMUP_API_KEY non risulta fra le variabili d'ambiente di QUESTO "
            "servizio. Se l'hai salvata su Render, controlla di averla messa "
            "sul servizio che serve il sito e di aver fatto un deploy dopo il "
            "salvataggio: le variabili si applicano solo al riavvio."
        )
    return diagnostica


@router.get("/stato")
@handle_errors
async def stato_sumup(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Verifica che la chiave API sia configurata e accettata da SumUp."""
    chiave = (settings.SUMUP_API_KEY or "").strip()
    merchant = (settings.SUMUP_MERCHANT_CODE or "").strip()

    stato: Dict[str, Any] = {
        "chiave_configurata": bool(chiave),
        "chiave_visibile": _mascherata(chiave),
        "merchant_code": merchant,
        "connessione_ok": False,
        "messaggio": "",
        "diagnostica": _diagnostica_ambiente(chiave, merchant),
    }

    if not chiave:
        stato["messaggio"] = (
            "Chiave API non configurata: aggiungi SUMUP_API_KEY tra le "
            "variabili d'ambiente e riavvia il servizio."
        )
        return stato

    # Il merchant code NON blocca piu' la verifica: e' ricavabile dalla chiave
    # stessa, e fermarsi qui nascondeva l'informazione che serve a impostarlo.
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            risposta = await client.get(
                f"{settings.SUMUP_API_BASE}/v0.1/me",
                headers={"Authorization": f"Bearer {chiave}"},
            )
    except httpx.HTTPError as exc:
        stato["messaggio"] = f"SumUp non raggiungibile: {type(exc).__name__}"
        return stato

    if risposta.status_code == 200:
        profilo = risposta.json() or {}
        conto = profilo.get("merchant_profile") or {}
        stato["connessione_ok"] = True
        stato["esercente"] = conto.get("company_name") or profilo.get("account", {}).get("username")
        merchant_reale = conto.get("merchant_code") or ""
        stato["merchant_code_reale"] = merchant_reale
        if not merchant:
            # La chiave funziona e dice a quale conto appartiene: si usa quello
            # invece di fermare tutto. Resta comunque scritto di fissarlo, cosi'
            # il controllo di appartenenza qui sotto torna a poter scattare.
            stato["merchant_code"] = merchant_reale
            stato["messaggio"] = (
                f"Connessione riuscita. SUMUP_MERCHANT_CODE non e' impostato: "
                f"uso il codice esercente della chiave ({merchant_reale}). "
                f"Conviene fissarlo fra le variabili d'ambiente."
            )
        elif merchant_reale and merchant_reale != merchant:
            # Chiave valida ma di un altro conto: leggeremmo le transazioni
            # sbagliate senza accorgercene.
            stato["connessione_ok"] = False
            stato["messaggio"] = (
                f"La chiave appartiene all'esercente {merchant_reale}, "
                f"ma e' configurato {merchant}. Correggi SUMUP_MERCHANT_CODE."
            )
        else:
            stato["messaggio"] = "Connessione a SumUp riuscita."
        return stato

    if risposta.status_code in (401, 403):
        stato["messaggio"] = (
            "SumUp rifiuta la chiave. Verifica di aver copiato la chiave "
            "creata e non la chiave pubblica mostrata in pagina."
        )
    else:
        stato["messaggio"] = f"SumUp ha risposto {risposta.status_code}."
    return stato


@router.get("/riepilogo")
@handle_errors
async def riepilogo_sumup(
    anno: int,
    mese: Optional[int] = None,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Riepilogo di sola lettura delle transazioni SumUp gia' acquisite.

    Non richiama la rete e non crea scritture: la pagina di coerenza mostra
    esclusivamente le prove archiviate dall'ultima sincronizzazione.
    """
    if mese is not None and not 1 <= int(mese) <= 12:
        raise HTTPException(status_code=400, detail="Mese non valido")
    mese_inizio = int(mese or 1)
    dal = date(int(anno), mese_inizio, 1)
    if mese is None:
        al = date(int(anno), 12, 31)
    elif int(mese) == 12:
        al = date(int(anno), 12, 31)
    else:
        al = date(int(anno), int(mese) + 1, 1) - timedelta(days=1)

    transazioni = await sumup_sync.transazioni_del_periodo(
        Database.get_db(), dal.isoformat(), al.isoformat()
    )
    giornate = sumup_sync.aggrega_per_giorno(transazioni)
    righe = [giornate[data] for data in sorted(giornate, reverse=True)]
    return {
        "configured": bool((settings.SUMUP_API_KEY or "").strip()),
        "anno": int(anno),
        "mese": mese,
        "totale_venduto": round(sum(r["vendite"] for r in righe), 2),
        "totale_rimborsi": round(sum(r["rimborsi"] for r in righe), 2),
        "totale_netto": round(sum(r["netto"] for r in righe), 2),
        "numero_transazioni": sum(int(r["transazioni"]) for r in righe),
        "giornalieri": righe,
        "fonte": "sumup_transactions_archiviate",
    }


def _intervallo_predefinito() -> tuple:
    """Ultimi otto giorni inclusi: recupera anche brevi interruzioni API."""
    oggi = date.today()
    return (oggi - timedelta(days=GIORNI_RECUPERO)).isoformat(), oggi.isoformat()


@router.post("/sincronizza")
@handle_errors
async def sincronizza_sumup(
    payload: Optional[Dict[str, Any]] = Body(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Scarica le transazioni SumUp e riallinea le chiusure del circuito.

    E' idempotente: rieseguirla sullo stesso intervallo non duplica ne'
    transazioni ne' movimenti di Prima Nota. Non crea ricavi — il ricavo e'
    gia' quello del corrispettivo XML, qui si stabilisce solo quanta parte
    e' passata dal terminale SumUp.
    """
    payload = payload or {}
    dal_predefinito, al_predefinito = _intervallo_predefinito()
    dal = str(payload.get("dal") or dal_predefinito)[:10]
    al = str(payload.get("al") or al_predefinito)[:10]
    for etichetta, valore in (("dal", dal), ("al", al)):
        try:
            date.fromisoformat(valore)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Data '{etichetta}' non valida: {valore!r} (attesa AAAA-MM-GG)",
            )
    if dal > al:
        raise HTTPException(status_code=400, detail="'dal' successivo ad 'al'")

    try:
        esito = await sumup_sync.sincronizza(
            Database.get_db(), dal, al, actor=current_user
        )
    except sumup_sync.SumUpNonConfigurato as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"SumUp non raggiungibile: {type(exc).__name__}",
        ) from exc

    giornate = esito.get("giornate") or []
    esito["message"] = (
        f"SumUp sincronizzato dal {dal} al {al}: {len(giornate)} giornate, "
        f"EUR {esito.get('totale_netto', 0):.2f} netti."
    )
    return esito


@router.get("/bonifica-pos-xml")
@handle_errors
async def analizza_bonifica_pos_xml(
    anno: Optional[int] = None,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Quante righe POS in Prima Nota derivano dall'XML. Sola lettura."""
    from app.services import bonifica_pos_xml

    return await bonifica_pos_xml.analizza(Database.get_db(), anno)


@router.post("/bonifica-pos-xml")
@handle_errors
async def applica_bonifica_pos_xml(
    payload: Optional[Dict[str, Any]] = Body(None),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Archivia le contropartite monetarie POS ricavate dall'XML.

    Non elimina prove: le conserva nello storico di audit, le esclude dai
    saldi operativi e ricrea soltanto le righe supportate da Numia/SumUp.

    Va confermata esplicitamente con ``{"conferma": true}``: tocca la
    contabilita' esistente e non deve poter partire per sbaglio.
    """
    from app.services import bonifica_pos_xml

    payload = payload or {}
    if payload.get("conferma") is not True:
        raise HTTPException(
            status_code=400,
            detail="Serve {\"conferma\": true}: la bonifica modifica righe di "
                   "Prima Nota gia' registrate. Usa prima la GET per vedere "
                   "quante sono.",
        )
    return await bonifica_pos_xml.applica(
        Database.get_db(), payload.get("anno"), actor=admin
    )


@router.post("/normalizza-descrizioni-pos")
@handle_errors
async def normalizza_descrizioni_pos(
    payload: Optional[Dict[str, Any]] = Body(None),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Porta le descrizioni storiche in formato italiano (gg/mm/aaaa).

    Correzione di sola forma: cambia il testo che si legge in Prima Nota, mai
    importi, date o fonti. Senza ``{"conferma": true}`` restituisce solo
    l'anteprima di cosa cambierebbe.
    """
    from app.services import bonifica_pos_xml

    payload = payload or {}
    return await bonifica_pos_xml.normalizza_descrizioni(
        Database.get_db(), payload.get("anno"),
        applica=payload.get("conferma") is True,
    )

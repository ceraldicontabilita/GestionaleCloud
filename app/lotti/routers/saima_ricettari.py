"""
Router per ricettari SAIMA S.p.a.
Fornisce i link ai PDF ricettari scaricabili dal sito SAIMA.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Depends
from pydantic import BaseModel
import httpx
import logging
import re
import unicodedata
import uuid
from typing import Optional
_LOG_INIT = logging.getLogger("uvicorn.error")
from bs4 import BeautifulSoup
from app.lotti.db import database as db
from datetime import datetime, timezone
from app.lotti.auth import require_admin

router = APIRouter(prefix="/saima/ricettari", tags=["saima"])

# Ricettari SAIMA — dati statici + link PDF
# Sezione Ricorrenze (6 ricettari)
RICETTARI_RICORRENZE = [
    {
        "id": "carnevale",
        "nome": "Carnevale",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/01/Ricettario-Carnevale.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/carnevale-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "prima-colazione",
        "nome": "Prima Colazione",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-prima-colazione.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/prima-colazione-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "dolci-easy",
        "nome": "Dolci Easy",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/ricettario-dolci-easy.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/dolci-easy-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "snack-take-away",
        "nome": "Snack Take Away",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-snack-take-away.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/snack-take-away-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "torroni",
        "nome": "Torroni",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/09/Ricettario-Torroni.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/torroni-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "halloween",
        "nome": "Halloween",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/09/Ricettario-halloween_2023.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/halloween-ricettario/",
        "sezione": "Ricorrenze",
    },
]

# Sezione Applicazioni Prodotto (19 ricettari)
RICETTARI_APPLICAZIONI = [
    {
        "id": "cometa-ricettario-natale",
        "nome": "Cometa Ricettario Natale",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2024/11/Cometa-sestino-SAIMA.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/cometa-ricettario-natale/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "ricettario-jolly-zelandia",
        "nome": "Ricettario Jolly Zelandia",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2024/11/Jolly-Saima.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/ricettario-jolly-zelandia/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "ricettario-bs-komplet",
        "nome": "Ricettario b+s Komplet",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2024/11/ricettario-bs.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/ricettario-bs-komplet/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "waldkorn-ricettario",
        "nome": "Waldkorn",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2024/11/Ricettario-Waldkorn.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/waldkorn-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "pan-della-vigna-ricettario",
        "nome": "Pan della Vigna",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/09/Ricettario-Pan-della-Vigna.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/pan-della-vigna-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "croissant-ricettario",
        "nome": "Croissant",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/07/Ricettario-Croissant.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/croissant-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "pancampagna-rustico-ricettario",
        "nome": "Pancampagna Rustico",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/06/Ricettario-pancampagna.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/pancampagna-rustico-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "rex-bucheron-ricettario",
        "nome": "Rex Bucheron",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/05/Ricettario-Bucheron.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/rex-bucheron-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "craft-malz-ricettario-2",
        "nome": "Craft Malz",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/05/Ricettario-Craft-Malz.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/craft-malz-ricettario-2/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "soft-break-ricettario",
        "nome": "Soft Break",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/02/Ricettario-Soft-Break.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/soft-break-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "cake-nature-ricettario",
        "nome": "Cake Nature",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/02/Ricettario-Cake-Nature-Braims-mod.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/cake-nature-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "chocospalmabili-bonfritto-e-forno",
        "nome": "Bonfritto e Forno (Choco Spalmabili)",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/12/Ricettario-Bonfritto-2.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/chocospalmabili-bonfritto-e-forno/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "5-ricette-in-5-minuti-ricettario",
        "nome": "5 Ricette in 5 Minuti",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/ricettario-5-ricette-in-5-minuti.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/5-ricette-in-5-minuti-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "choquit-ricettario",
        "nome": "Choquit",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Choquit.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/choquit-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "pasticceria-mignon-ricettario",
        "nome": "Pasticceria Mignon",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-pasticceria-mignon-debic.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/pasticceria-mignon-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "creme-con-cioccolato-callebaut-ricettario",
        "nome": "Creme con Cioccolato Callebaut",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/08/Ricettario-creme-con-cioccolato-callebaut.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/creme-con-cioccolato-callebaut-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "mix-savoiardo-ricettario",
        "nome": "Mix Savoiardo",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/08/Ricettario-italmill-mix-savoiardo.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/mix-savoiardo-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "scrocchiarella-ricettario",
        "nome": "Scrocchiarella",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Scrocchiarella-new.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/scrocchiarella-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "mix-muffin-ricettario",
        "nome": "Mix Muffin",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Mix-muffin.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/mix-muffin-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
]

# La pagina ufficiale corrente espone 19 applicazioni. I sei vecchi link
# "Ricorrenze" sono mantenuti sopra come memoria di migrazione ma non vengono
# più mostrati: alcuni restituiscono 404 e confondevano l'operatore.
RICETTARI_STATICI = RICETTARI_APPLICAZIONI
ALL_RICETTARI_STATICI = RICETTARI_STATICI

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
}


@router.get("")
async def get_ricettari():
    """Restituisce i soli ricettari SAIMA con link PDF e numero ricette estratte."""
    # Prima controlla se ci sono ricettari extra in DB
    db_extra = await db.saima_ricettari.find({}, {"_id": 0}).to_list(100)

    # Prende solo quelli non già presenti nella lista statica
    ids_statici = {r["id"] for r in ALL_RICETTARI_STATICI}
    nuovi = [extra for extra in db_extra if extra.get("id") not in ids_statici]

    return list(ALL_RICETTARI_STATICI) + nuovi


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())



async def _chiave_ingrediente_canonica(nome: str) -> str:
    """Restituisce la chiave del matcher unico Lotti.

    Ricette, righe XML e lotti residui convergono sullo stesso ingrediente
    canonico. Non vengono create equivalenze per somiglianza testuale.
    """
    from app.lotti.routers.ingredienti import _consolida_canonico, match_livello2
    from app.lotti.routers.lotti_fornitori import calcola_nome_canonico

    canonico = await calcola_nome_canonico(nome, usa_llm=False)
    canonico = match_livello2(canonico or nome) or canonico or nome
    return _norm(_consolida_canonico(canonico))


def _quantita_richiesta(ingredient: dict, factor: float) -> dict:
    return {
        "valore": round(float(ingredient.get("quantita") or 0) * factor, 3),
        "unita": ingredient.get("unita_misura") or "",
    }


def _quantita_base(value: float, unit: str) -> tuple[float, str]:
    normalized = str(unit or "").strip().lower().replace(".", "")
    number = float(value or 0)
    if normalized in {"kg"}:
        return number * 1000, "g"
    if normalized in {"g", "gr", "mg"}:
        return (number / 1000 if normalized == "mg" else number), "g"
    if normalized in {"l", "lt"}:
        return number * 1000, "ml"
    if normalized in {"ml", "cl"}:
        return (number * 10 if normalized == "cl" else number), "ml"
    if normalized in {"pz", "pze", "nr", "n", "conf", "cf"}:
        return number, "pz"
    return number, normalized


class VerificaDisponibilitaPayload(BaseModel):
    pezzi: Optional[float] = None


@router.post("/ricette/{ricetta_id}/verifica-disponibilita")
async def verifica_disponibilita_ricetta(ricetta_id: str, body: VerificaDisponibilitaPayload):
    """Confronta ricetta e giacenze con il matcher canonico dei Lotti.

    Una fattura prova l'acquisto storico; solo un lotto residuo prova la
    disponibilità. Il confronto usa il nome canonico comune, senza suggerire
    sostituzioni generiche che modificherebbero ricetta, gusto o allergeni.
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")

    base = float(ricetta.get("porzioni") or ricetta.get("pezzi_ricetta_base") or 0)
    pezzi = float(body.pezzi or base or 0)
    factor = (pezzi / base) if base > 0 and pezzi > 0 else 1.0
    lotti = await db.lotti_fornitori.find(
        {"esaurito": {"$ne": True}, "quantita_disponibile": {"$gt": 0}},
        {
            "_id": 0,
            "id": 1,
            "prodotto_nome": 1,
            "prodotto_nome_norm": 1,
            "quantita_disponibile": 1,
            "unita_misura": 1,
            "fornitore": 1,
            "fattura_ref": 1,
            "data_fattura": 1,
        },
    ).to_list(12000)

    disponibili: dict[str, dict] = {}
    chiavi_lotti: dict[str, str] = {}
    for lotto in lotti:
        nome = lotto.get("prodotto_nome_norm") or lotto.get("prodotto_nome") or ""
        nome_norm = _norm(nome)
        if not nome_norm:
            continue
        if nome_norm not in chiavi_lotti:
            chiavi_lotti[nome_norm] = await _chiave_ingrediente_canonica(nome)
        chiave = chiavi_lotti[nome_norm]
        if not chiave:
            continue

        valore, unita_base = _quantita_base(
            lotto.get("quantita_disponibile") or 0,
            lotto.get("unita_misura") or "",
        )
        aggregato = disponibili.setdefault(
            chiave,
            {
                **lotto,
                "prodotto_nome": nome,
                "ingrediente_canonico": chiave,
                "quantita_disponibile": 0.0,
                "quantita_base": 0.0,
                "unita_base": unita_base,
                "fatture": [],
            },
        )
        if aggregato.get("unita_base") == unita_base:
            aggregato["quantita_base"] += valore
            aggregato["quantita_disponibile"] += float(lotto.get("quantita_disponibile") or 0)
        riferimento = lotto.get("fattura_ref")
        if riferimento and riferimento not in aggregato["fatture"]:
            aggregato["fatture"].append(riferimento)

    righe = []
    for ingrediente in ricetta.get("ingredienti_dettaglio") or []:
        nome = (ingrediente.get("nome") or "").strip()
        if not nome:
            continue
        richiesta = _quantita_richiesta(ingrediente, factor)
        if _norm(nome) == "acqua":
            righe.append(
                {
                    "ingrediente": nome,
                    "stato": "disponibile",
                    "richiesta": richiesta,
                    "prodotto": {"nome": "Acqua di laboratorio", "fonte": "disponibilità interna"},
                    "alternative": [],
                }
            )
            continue

        chiave = await _chiave_ingrediente_canonica(nome)
        disponibile = disponibili.get(chiave)
        richiesta_base, unita_richiesta = _quantita_base(richiesta["valore"], richiesta["unita"])
        sufficiente = bool(disponibile) and (
            richiesta_base <= 0
            or not unita_richiesta
            or (
                unita_richiesta == disponibile.get("unita_base")
                and float(disponibile.get("quantita_base") or 0) >= richiesta_base
            )
        )
        if sufficiente:
            righe.append(
                {
                    "ingrediente": nome,
                    "stato": "disponibile",
                    "richiesta": richiesta,
                    "prodotto": {
                        "id": disponibile.get("id"),
                        "nome": disponibile.get("prodotto_nome"),
                        "ingrediente_canonico": chiave,
                        "quantita_disponibile": round(disponibile.get("quantita_disponibile", 0), 3),
                        "unita": disponibile.get("unita_misura", ""),
                        "fornitore": disponibile.get("fornitore", ""),
                        "fatture": disponibile.get("fatture", [])[:5],
                    },
                    "alternative": [],
                }
            )
            continue

        if disponibile:
            righe.append(
                {
                    "ingrediente": nome,
                    "stato": "da_acquistare",
                    "richiesta": richiesta,
                    "prodotto": {
                        "id": disponibile.get("id"),
                        "nome": disponibile.get("prodotto_nome"),
                        "ingrediente_canonico": chiave,
                        "quantita_disponibile": round(disponibile.get("quantita_base", 0), 3),
                        "unita": disponibile.get("unita_base", ""),
                        "fornitore": disponibile.get("fornitore", ""),
                        "fatture": disponibile.get("fatture", [])[:5],
                        "insufficiente": True,
                    },
                    "motivo": "Giacenza insufficiente per la quantità richiesta.",
                    "mancante": {
                        "valore": round(
                            max(0, richiesta_base - float(disponibile.get("quantita_base") or 0)),
                            3,
                        ),
                        "unita": unita_richiesta,
                    },
                    "alternative": [],
                }
            )
            continue

        righe.append(
            {
                "ingrediente": nome,
                "stato": "da_acquistare",
                "richiesta": richiesta,
                "prodotto": None,
                "alternative": [],
            }
        )

    da_acquistare = [riga for riga in righe if riga["stato"] == "da_acquistare"]
    return {
        "ricetta_id": ricetta_id,
        "ricetta_nome": ricetta.get("nome"),
        "pezzi_richiesti": pezzi or None,
        "resa_base": base or None,
        "resa_da_impostare": base <= 0,
        "moltiplicatore": round(factor, 4),
        "realizzabile_subito": not da_acquistare,
        "realizzabile_con_sostituzioni": False,
        "righe": righe,
        "totali": {
            "disponibili": len([riga for riga in righe if riga["stato"] == "disponibile"]),
            "sostituibili": 0,
            "da_acquistare": len(da_acquistare),
        },
    }

class ListaSpesaPayload(BaseModel):
    pezzi: Optional[float] = None


@router.post("/ricette/{ricetta_id}/aggiungi-mancanti-carrello")
async def aggiungi_mancanti_carrello(
    ricetta_id: str,
    body: ListaSpesaPayload,
    _admin=Depends(require_admin),
):
    verifica = await verifica_disponibilita_ricetta(
        ricetta_id, VerificaDisponibilitaPayload(pezzi=body.pezzi)
    )
    mancanti = [row for row in verifica["righe"] if row["stato"] == "da_acquistare"]
    doc = await db.carrello_sospesi.find_one({"_id": "default"}, {"_id": 0}) or {}
    current = list(doc.get("righe") or [])
    existing = {_norm(item.get("nome")) for item in current}
    added = []
    for row in mancanti:
        if _norm(row["ingrediente"]) in existing:
            continue
        da_comprare = row.get("mancante") or row["richiesta"]
        item = {
            "id": f"ricetta-saima-{uuid.uuid4()}",
            "nome": row["ingrediente"],
            "quantita": max(1, da_comprare["valore"] or 1),
            "unita": da_comprare["unita"] or "conf",
            "prezzo": 0,
            "fornitore": "SAIMA",
            "fonte": "ricetta_saima",
            "ricetta_id": ricetta_id,
            "nota": "Ingrediente mancante rilevato dalla verifica della ricetta; prezzo da confermare.",
        }
        current.append(item)
        existing.add(_norm(row["ingrediente"]))
        added.append(item)
    await db.carrello_sospesi.update_one(
        {"_id": "default"},
        {"$set": {"righe": current, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "aggiunti": len(added), "gia_presenti": len(mancanti) - len(added), "righe": added}


@router.get("/pdf-proxy")
async def proxy_pdf(url: str = Query(..., description="URL del PDF da proxare")):
    """
    Proxy backend per visualizzare PDF SAIMA inline nell'app.
    Scarica il PDF da SAIMA e lo restituisce con gli header corretti per l'embedding.
    """
    import urllib.parse

    # Whitelist: domini autorizzati
    DOMINI_AUTORIZZATI = {
        "saimaspa.com",
        "www.saimaspa.com",
        "mepaalimentari.com",
        "www.mepaalimentari.com",
    }
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc not in DOMINI_AUTORIZZATI:
        raise HTTPException(status_code=403, detail=f"URL non autorizzato: {parsed.netloc}")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers=HEADERS)
            if r.status_code != 200:
                raise HTTPException(
                    status_code=502, detail=f"PDF non disponibile: HTTP {r.status_code}"
                )
            content_type = r.headers.get("content-type", "application/pdf")
            if "html" in content_type.lower():
                raise HTTPException(
                    status_code=502, detail="Il server ha restituito HTML invece del PDF"
                )
            from fastapi.responses import Response

            return Response(
                content=r.content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "inline",
                    "Cache-Control": "public, max-age=3600",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Errore download PDF: {str(e)}")


@router.post("/aggiorna")
async def aggiorna_ricettari(background_tasks: BackgroundTasks):
    """Tenta di recuperare ricettari aggiuntivi dal sito SAIMA (esegue in background)."""

    async def esegui():
        sezioni = [
            "https://www.saimaspa.com/applicazioni-prodotto/",
        ]
        found = []
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                for sezione in sezioni:
                    r = await client.get(sezione, headers=HEADERS)
                    soup = BeautifulSoup(r.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/default-item/" in href:
                            nome = a.get_text(strip=True)
                            if nome and href not in [x["url_pagina"] for x in found]:
                                found.append({"nome": nome, "url_pagina": href})

                # Per ognuno recupera il link PDF
                for item in found:
                    rid = item["url_pagina"].split("/default-item/")[-1].strip("/")
                    # Evita duplicati con statici
                    if any(r["id"] == rid for r in RICETTARI_STATICI):
                        continue
                    try:
                        r = await client.get(item["url_pagina"], headers=HEADERS)
                        soup = BeautifulSoup(r.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            if (
                                ".pdf" in a["href"].lower()
                                and "Privacy" not in a.get_text()
                                and "Cookie" not in a.get_text()
                            ):
                                ricettario = {
                                    "id": rid,
                                    "nome": item["nome"].replace(" – Ricettario", "").strip(),
                                    "url_pdf": a["href"],
                                    "url_pagina": item["url_pagina"],
                                    "sezione": "Aggiornato",
                                    "data_aggiornamento": datetime.now(timezone.utc).isoformat(),
                                }
                                await db.saima_ricettari.update_one(
                                    {"id": rid}, {"$set": ricettario}, upsert=True
                                )
                                break
                    except Exception:
                        _LOG_INIT.debug("[saima_ricettari] errore non bloccante ignorato")
        except Exception as e:
            print(f"[SAIMA Ricettari] Errore aggiornamento: {e}")

    background_tasks.add_task(esegui)
    return {"message": "Aggiornamento ricettari avviato in background"}


class NuovoRicettario(BaseModel):
    nome: str
    url_pdf: str
    sezione: str = "Altro"
    fornitore: str = ""


@router.post("/aggiungi")
async def aggiungi_ricettario(body: NuovoRicettario):
    """Aggiunge un ricettario SAIMA custom tramite URL PDF diretto."""
    import re, urllib.parse

    # Genera ID univoco dal nome
    rid = re.sub(r"[^a-z0-9]+", "-", body.nome.lower()).strip("-")
    # Verifica URL
    parsed = urllib.parse.urlparse(body.url_pdf)
    if not parsed.scheme.startswith("http"):
        raise HTTPException(400, "URL non valido")
    doc = {
        "id": rid,
        "nome": body.nome.strip(),
        "url_pdf": body.url_pdf.strip(),
        "url_pagina": body.url_pdf,
        "sezione": body.sezione,
        "fornitore": body.fornitore,
        "aggiunto_manualmente": True,
        "data_aggiornamento": datetime.now(timezone.utc).isoformat(),
    }
    await db.saima_ricettari.update_one({"id": rid}, {"$set": doc}, upsert=True)
    return {"success": True, "id": rid, "nome": body.nome}


@router.delete("/{ricettario_id}")
async def elimina_ricettario(ricettario_id: str):
    """Elimina un ricettario custom dal DB (non quelli statici SAIMA)."""
    # Verifica non sia uno statico
    ids_statici = {r["id"] for r in ALL_RICETTARI_STATICI}
    if ricettario_id in ids_statici:
        raise HTTPException(400, "Non puoi eliminare i ricettari SAIMA statici")
    r = await db.saima_ricettari.delete_one({"id": ricettario_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Ricettario non trovato")
    return {"success": True}

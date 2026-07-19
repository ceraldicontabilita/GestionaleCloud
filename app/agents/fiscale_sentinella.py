import re
import asyncio
import base64
import logging
from datetime import datetime, timezone, date, timedelta
from app.agents.notifier import crea_segnalazione

logger = logging.getLogger(__name__)


def _estrai_testo_pdf(pdf_bytes: bytes) -> str:
    """Estrae testo da PDF con pdfplumber (OCR semplice)."""
    try:
        import pdfplumber
        import io
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            testi = []
            for page in pdf.pages[:5]:  # max 5 pagine
                t = page.extract_text()
                if t:
                    testi.append(t)
            return "\n".join(testi)
    except Exception as e:
        logger.warning(f"pdfplumber fallito: {e}")
        return ""


class FiscaleSentinella:
    PATTERN_AVVISO_BONARIO = [
        "avviso bonario", "comunicazione di irregolarit",
        "art. 36-bis", "art. 36-ter", "art. 54-bis",
        "liquidazione automatica", "D.Lgs. 462/97",
        "sanzione ridotta", "pagamento entro 30 giorni"
    ]
    CODICI_RAVVEDIMENTO = [
        '8901', '8902', '8903', '8904', '8906', '8907',
        '8911', '8913', '8918', '8926', '8929'
    ]

    async def run(self, db):
        await asyncio.gather(
            self._analizza_email(db),
            self._controlla_scadenze_f24(db),
        )

    async def _analizza_email(self, db):
        docs = await db["documents_inbox"].find({
            "agente_fiscale_processato": {"$ne": True},
            "$or": [
                {"categoria": "fisco"},
                {"mittente": {"$regex": "agenziaentrate|agenzia.entrate|fisconline", "$options": "i"}},
                {"filename": {"$regex": "avviso|bonario|irregolarit", "$options": "i"}}
            ]
        }, {"_id": 0}).to_list(30)

        for doc in docs:
            # Estrai testo da PDF se presente
            testo_pdf = ""
            if doc.get("pdf_data") or doc.get("content_base64"):
                try:
                    raw = doc.get("pdf_data") or doc.get("content_base64", "")
                    pdf_bytes = base64.b64decode(raw) if raw else b""
                    if pdf_bytes:
                        testo_pdf = _estrai_testo_pdf(pdf_bytes)
                        if testo_pdf:
                            await db["documents_inbox"].update_one(
                                {"id": doc["id"]},
                                {"$set": {"testo_estratto_ocr": testo_pdf[:5000]}}
                            )
                except Exception as e:
                    logger.warning(f"OCR PDF doc {doc.get('id')}: {e}")

            testo = (
                doc.get("testo_estratto", "") + " " +
                testo_pdf + " " +
                doc.get("oggetto", "") + " " +
                doc.get("filename", "")
            ).lower()
            is_avviso = any(p in testo for p in self.PATTERN_AVVISO_BONARIO)
            if is_avviso:
                await self._processa_avviso_bonario(db, doc, testo)
            await db["documents_inbox"].update_one(
                {"id": doc["id"]},
                {"$set": {
                    "agente_fiscale_processato": True,
                    "agente_fiscale_tipo": "avviso_bonario" if is_avviso else "altro"
                }}
            )

    async def _processa_avviso_bonario(self, db, doc, testo: str = None):
        if testo is None:
            testo = (doc.get("testo_estratto", "") + " " + doc.get("oggetto", ""))
        avviso = self._estrai_dati_avviso(testo)
        codice = avviso.get("codice_tributo")
        periodo = avviso.get("periodo_riferimento")
        importo = avviso.get("importo_tributo", 0)
        scadenza = avviso.get("scadenza_pagamento")

        f24_pagato = None
        if codice and periodo:
            f24_pagato = await db["f24_unificato"].find_one({
                "codici_univoci": {"$in": [codice]},
                "periodo_riferimento": {"$regex": periodo[:7] if periodo else ""},
                "status": "pagato"
            })

        f24_ravveduto = await db["f24_unificato"].find_one({
            "has_ravvedimento": True,
            "codici_univoci": {"$in": [codice] if codice else []},
            "status": "pagato"
        }) if codice else None

        if f24_ravveduto:
            tipo = "info"
            titolo = f"Avviso bonario {codice} — già ravveduto"
            desc = (
                f"L'avviso bonario per codice {codice} periodo {periodo} "
                f"risulta già sanato con ravvedimento operoso. "
                f"L'avviso può essere ignorato. Archivia il documento."
            )
            azione = "Archivia — già risolto con ravvedimento"
        elif f24_pagato:
            tipo = "avviso"
            titolo = f"Avviso bonario {codice} — sembra già pagato"
            desc = (
                f"Ho ricevuto un avviso bonario per {codice} periodo {periodo} "
                f"(€{importo:.2f}). Risulta già pagato con F24 del "
                f"{f24_pagato.get('data_scadenza', 'N/D')}. "
                f"Probabile ritardo ADE nel registrare il pagamento. "
                f"Conserva la quietanza e attendi. Se persiste, contatta il commercialista."
            )
            azione = "Verifica quietanza F24 già pagato"
        else:
            giorni = None
            if scadenza:
                try:
                    giorni = (date.fromisoformat(scadenza) - date.today()).days
                except Exception:
                    pass
            tipo = "urgente" if (giorni and giorni < 15) else "avviso"
            titolo = f"Avviso bonario DA PAGARE — {codice}"
            desc = (
                f"Avviso bonario ADE per codice {codice} periodo {periodo}. "
                f"Importo: €{importo:.2f}. "
                f"Se pagato entro 30 giorni la sanzione è ridotta al 10%. "
                f"Scadenza: {scadenza or 'da verificare nel documento'}. "
                f"{'URGENTE: mancano ' + str(giorni) + ' giorni!' if giorni and giorni < 15 else ''} "
                f"Invia subito al commercialista per preparare l'F24."
            )
            azione = f"Invia al commercialista — scadenza {scadenza}"

        await crea_segnalazione(
            db, agente="FiscaleSentinella", tipo=tipo,
            titolo=titolo, descrizione=desc, azione=azione,
            dati={
                "documento_id": doc.get("id"),
                "codice_tributo": codice,
                "periodo": periodo,
                "importo": importo,
                "f24_pagato_id": f24_pagato.get("id") if f24_pagato else None
            },
            scadenza=scadenza
        )

    def _estrai_dati_avviso(self, testo: str) -> dict:
        dati = {}
        m = re.search(r'codice\s*tributo[:\s]+(\d{4})', testo, re.I)
        if m:
            dati["codice_tributo"] = m.group(1)
        m = re.search(r'periodo[:\s]+(\d{2}/\d{4})', testo, re.I)
        if m:
            dati["periodo_riferimento"] = m.group(1)
        # "tributo" NON è tra le parole-chiave: "Codice Tributo: 9001" (il
        # codice a 4 cifre, non l'importo) verrebbe altrimenti scambiato per
        # l'importo, perché la ricerca prende il primo match nel testo e
        # "codice tributo" precede quasi sempre "importo" in un avviso reale.
        m = re.search(r'(?:imposta|importo)[:\s]+€?\s*([\d.,]+)', testo, re.I)
        if m:
            try:
                dati["importo_tributo"] = float(m.group(1).replace('.', '').replace(',', '.'))
            except Exception:
                pass
        m = re.search(r'(?:entro il|scadenza)[:\s]+(\d{2}/\d{2}/\d{4})', testo, re.I)
        if m:
            p = m.group(1).split("/")
            if len(p) == 3:
                dati["scadenza_pagamento"] = f"{p[2]}-{p[1]}-{p[0]}"
        return dati

    async def _controlla_scadenze_f24(self, db):
        oggi = date.today()
        tra15 = (oggi + timedelta(days=15)).isoformat()
        f24_urgenti = await db["f24_unificato"].find({
            "status": "da_pagare",
            "data_scadenza": {"$gte": oggi.isoformat(), "$lte": tra15}
        }, {"_id": 0}).to_list(20)

        for f24 in f24_urgenti:
            esistente = await db["agenti_segnalazioni"].find_one({
                "agente": "FiscaleSentinella",
                "dati_riferimento.f24_id": f24["id"],
                "risolta": {"$ne": True}
            })
            if not esistente:
                try:
                    giorni = (
                        datetime.fromisoformat(f24["data_scadenza"]).date() - oggi
                    ).days
                except Exception:
                    giorni = "?"
                await crea_segnalazione(
                    db, agente="FiscaleSentinella", tipo="urgente",
                    titolo=f"F24 in scadenza — {f24.get('descrizione', 'N/D')}",
                    descrizione=(
                        f"F24 {f24.get('descrizione', '')} scade "
                        f"il {f24.get('data_scadenza', '')}. "
                        f"Mancano {giorni} giorni. Importo: €{f24.get('importo', 0):.2f}. "
                        f"Invia al commercialista per preparazione pagamento."
                    ),
                    azione="F24 → visualizza e prepara pagamento",
                    dati={"f24_id": f24["id"]},
                    scadenza=f24.get("data_scadenza")
                )

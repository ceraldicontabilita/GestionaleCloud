import re
import asyncio
from datetime import datetime, timezone, date, timedelta
from app.agents.notifier import crea_segnalazione


class HRGuardiano:
    CF_PATTERN = r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])'

    async def run(self, db):
        await asyncio.gather(
            self._controlla_dimissioni_email(db),
            self._controlla_scadenze_contratti(db),
            self._controlla_libretti_sanitari(db),
            self._riconcilia_cedolini(db),
        )

    async def _controlla_dimissioni_email(self, db):
        emails = await db["documents_inbox"].find({
            "agente_hr_processato": {"$ne": True},
            "$or": [
                {"oggetto": {"$regex": "recesso|dimissioni|cessazione", "$options": "i"}},
                {"mittente": {"$regex": "minlavoro|cliclavoro", "$options": "i"}},
                {"filename": {"$regex": r"B\d{5,}_[A-Z]{6}\d{2}", "$options": "i"}}
            ]
        }, {"_id": 0}).to_list(10)

        for email_doc in emails:
            testo = (
                email_doc.get("testo_estratto", "") + " " +
                email_doc.get("filename", "") + " " +
                email_doc.get("oggetto", "")
            ).upper()
            cf_match = re.search(self.CF_PATTERN, testo)
            if cf_match:
                cf = cf_match.group(1)
                dip = await db["dipendenti"].find_one(
                    {"$or": [{"codice_fiscale": cf}, {"cf": cf}]},
                    {"_id": 0}
                )
                if dip:
                    data_dim = None
                    m = re.search(r'_(20\d{6})', email_doc.get("filename", ""))
                    if m:
                        d = m.group(1)
                        data_dim = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                    await crea_segnalazione(
                        db, agente="HRGuardiano", tipo="avviso",
                        titolo=f"Dimissioni telematiche — {dip.get('nome_completo', cf)}",
                        descrizione=(
                            f"Ricevuta comunicazione dimissioni per {dip.get('nome_completo', cf)} (CF: {cf}). "
                            f"Data decorrenza: {data_dim or 'da verificare'}. "
                            f"Azioni: 1) Conferma data ultimo giorno. "
                            f"2) Calcola TFR e liquidazione. "
                            f"3) Emetti cedolino finale. "
                            f"4) Comunica al consulente per UNILAV cessazione."
                        ),
                        azione="Dipendenti → scheda → avvia procedura uscita",
                        dati={
                            "dipendente_id": dip.get("id"),
                            "cf": cf,
                            "data_dimissioni": data_dim,
                            "documento_id": email_doc.get("id")
                        }
                    )
                    if data_dim:
                        await db["dipendenti"].update_one(
                            {"id": dip["id"]},
                            {"$set": {
                                "stato": "in_uscita",
                                "data_dimissioni_comunicata": data_dim,
                                "documento_dimissioni_id": email_doc.get("id")
                            }}
                        )
            await db["documents_inbox"].update_one(
                {"id": email_doc["id"]},
                {"$set": {"agente_hr_processato": True}}
            )

    async def _controlla_scadenze_contratti(self, db):
        oggi = date.today()
        tra30 = (oggi + timedelta(days=30)).isoformat()
        contratti = await db["dipendenti"].find({
            "tipo_contratto": {"$in": ["Tempo Determinato", "Part-Time Determinato"]},
            "data_fine_contratto": {"$gte": oggi.isoformat(), "$lte": tra30},
            "stato": {"$ne": "cessato"}
        }, {"_id": 0, "id": 1, "nome_completo": 1, "data_fine_contratto": 1, "mansione": 1}).to_list(20)

        for dip in contratti:
            esistente = await db["agenti_segnalazioni"].find_one({
                "agente": "HRGuardiano",
                "dati_riferimento.dipendente_id": dip["id"],
                "titolo": {"$regex": "Scadenza contratto"},
                "risolta": {"$ne": True}
            })
            if esistente:
                continue
            data_fine = dip.get("data_fine_contratto", "")
            try:
                giorni = (date.fromisoformat(data_fine) - oggi).days
            except Exception:
                giorni = "?"
            await crea_segnalazione(
                db, agente="HRGuardiano",
                tipo="urgente" if isinstance(giorni, int) and giorni < 15 else "avviso",
                titolo=f"Scadenza contratto — {dip.get('nome_completo', '')}",
                descrizione=(
                    f"Contratto {dip.get('nome_completo', '')} ({dip.get('mansione', '')}) "
                    f"scade il {data_fine}. Mancano {giorni} giorni. "
                    f"Decide: proroga, trasformazione a indeterminato, o cessazione. "
                    f"La comunicazione UNILAV va fatta PRIMA della scadenza."
                ),
                azione="Dipendenti → contratti → rinnova o cessazione",
                dati={"dipendente_id": dip["id"], "data_fine": data_fine},
                scadenza=data_fine
            )

    async def _controlla_libretti_sanitari(self, db):
        oggi = date.today()
        tra60 = (oggi + timedelta(days=60)).isoformat()
        dipendenti = await db["dipendenti"].find(
            {
                "libretto_sanitario_scadenza": {"$gte": oggi.isoformat(), "$lte": tra60},
                "stato": {"$ne": "cessato"}
            },
            {"_id": 0, "id": 1, "nome_completo": 1, "libretto_sanitario_scadenza": 1}
        ).to_list(20)
        for dip in dipendenti:
            await crea_segnalazione(
                db, agente="HRGuardiano", tipo="avviso",
                titolo=f"Libretto sanitario in scadenza — {dip.get('nome_completo', '')}",
                descrizione=(
                    f"Il libretto sanitario di {dip.get('nome_completo', '')} "
                    f"scade il {dip.get('libretto_sanitario_scadenza', '')}. "
                    f"Prenota visita medica competente entro questa data."
                ),
                azione="Dipendenti → anagrafica → libretto sanitario",
                dati={"dipendente_id": dip["id"]},
                scadenza=dip.get("libretto_sanitario_scadenza")
            )

    async def _riconcilia_cedolini(self, db):
        anno = datetime.now().year
        salari_pending = await db["prima_nota_salari"].find(
            {"anno": anno, "riconciliato": {"$ne": True}}, {"_id": 0}
        ).to_list(100)

        for salario in salari_pending:
            nome = salario.get("dipendente_nome", "")
            importo = float(salario.get("importo", 0))
            mese = salario.get("mese")
            if not nome or importo <= 0 or not mese:
                continue
            try:
                mese_int = int(mese)
            except Exception:
                continue
            mese_succ = (mese_int % 12) + 1
            anno_succ = anno + 1 if mese_int == 12 else anno
            data_da = f"{anno}-{mese_int:02d}-25"
            data_a = f"{anno_succ}-{mese_succ:02d}-10"
            mov = await db["estratto_conto_movimenti"].find_one({
                "riconciliato": {"$ne": True},
                "data": {"$gte": data_da, "$lte": data_a},
                "importo": {"$gte": -(importo + 2), "$lte": -(importo - 2)},
                "$or": [
                    {"descrizione": {"$regex": nome.split()[0][:8], "$options": "i"}},
                    {"descrizione_originale": {"$regex": nome.split()[0][:8], "$options": "i"}}
                ]
            })
            if mov:
                await db["prima_nota_salari"].update_one(
                    {"id": salario["id"]},
                    {"$set": {
                        "riconciliato": True,
                        "estratto_conto_id": str(mov.get("id", mov["_id"])),
                        "riconciliato_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                await db["estratto_conto_movimenti"].update_one(
                    {"_id": mov["_id"]},
                    {"$set": {
                        "riconciliato": True,
                        "riconciliato_con": "prima_nota_salari",
                        "salario_id": salario["id"]
                    }}
                )

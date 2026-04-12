"""
Privacy Policy e Terms of Service per Meta/WhatsApp compliance.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

PRIVACY_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Informativa sulla Privacy — Ceraldi Group S.R.L.</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.7; }
h1 { color: #1a40b5; border-bottom: 3px solid #1a40b5; padding-bottom: 12px; }
h2 { color: #334155; margin-top: 32px; }
.info { background: #f0f4ff; padding: 16px; border-radius: 8px; margin: 20px 0; }
</style>
</head>
<body>
<h1>Informativa sulla Privacy</h1>
<p><strong>Ceraldi Group S.R.L.</strong> — P.IVA 04523831214<br>
Piazza Carità 14, 80134 Napoli (NA)<br>
Email: ceraldigroupsrl@gmail.com</p>

<div class="info">
Questa informativa è resa ai sensi dell'art. 13 del Regolamento UE 2016/679 (GDPR) e descrive le modalità di trattamento dei dati personali tramite il sistema gestionale Ceraldi ERP e le notifiche WhatsApp Business.
</div>

<h2>1. Titolare del Trattamento</h2>
<p>Il Titolare del trattamento è <strong>Ceraldi Group S.R.L.</strong>, con sede in Piazza Carità 14, 80134 Napoli (NA), P.IVA 04523831214.</p>

<h2>2. Dati Trattati</h2>
<p>Tramite il sistema gestionale e il servizio WhatsApp Business trattiamo:</p>
<ul>
<li><strong>Dati dei dipendenti</strong>: nome, cognome, codice fiscale, IBAN, recapito telefonico per l'invio di cedolini e comunicazioni aziendali</li>
<li><strong>Dati dei fornitori</strong>: denominazione, P.IVA, dati di contatto per la gestione del ciclo passivo</li>
<li><strong>Dati contabili</strong>: fatture, movimenti bancari, corrispettivi per la gestione amministrativa</li>
</ul>

<h2>3. Finalità del Trattamento</h2>
<ul>
<li>Gestione amministrativa e contabile dell'attività</li>
<li>Invio cedolini e comunicazioni HR ai dipendenti via WhatsApp</li>
<li>Notifiche operative giornaliere ai soci (scadenze, incassi, stato contabile)</li>
<li>Adempimenti fiscali obbligatori</li>
</ul>

<h2>4. Base Giuridica</h2>
<p>Il trattamento è basato su:</p>
<ul>
<li>Esecuzione del contratto di lavoro (art. 6.1.b GDPR) per i dati dei dipendenti</li>
<li>Obblighi legali (art. 6.1.c GDPR) per adempimenti fiscali e contabili</li>
<li>Legittimo interesse (art. 6.1.f GDPR) per le notifiche operative interne</li>
</ul>

<h2>5. Conservazione dei Dati</h2>
<p>I dati sono conservati per il periodo necessario alle finalità per cui sono raccolti e comunque non oltre i termini previsti dalla normativa fiscale italiana (10 anni per i documenti contabili).</p>

<h2>6. Comunicazione a Terzi</h2>
<p>I dati possono essere comunicati a:</p>
<ul>
<li>Meta Platforms Ireland Limited (per il servizio WhatsApp Business API)</li>
<li>MongoDB, Inc. (per l'hosting del database)</li>
<li>Consulente del lavoro per gli adempimenti HR</li>
</ul>

<h2>7. Diritti dell'Interessato</h2>
<p>L'interessato può esercitare i diritti di cui agli artt. 15-22 del GDPR (accesso, rettifica, cancellazione, limitazione, portabilità, opposizione) scrivendo a <strong>ceraldigroupsrl@gmail.com</strong>.</p>

<h2>8. Eliminazione dei Dati</h2>
<p>Per richiedere l'eliminazione dei propri dati, inviare una email a <strong>ceraldigroupsrl@gmail.com</strong> con oggetto "Richiesta cancellazione dati" specificando i dati da eliminare.</p>

<p><em>Ultimo aggiornamento: Aprile 2026</em></p>
</body>
</html>"""

TERMS_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Condizioni d'Uso — Ceraldi Group S.R.L.</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.7; }
h1 { color: #1a40b5; border-bottom: 3px solid #1a40b5; padding-bottom: 12px; }
h2 { color: #334155; margin-top: 32px; }
</style>
</head>
<body>
<h1>Condizioni d'Uso</h1>
<p><strong>Ceraldi Group S.R.L.</strong> — P.IVA 04523831214</p>

<h2>1. Descrizione del Servizio</h2>
<p>Il sistema Ceraldi ERP è un gestionale aziendale ad uso interno di Ceraldi Group S.R.L. per la gestione contabile, HR, magazzino e comunicazioni aziendali tramite WhatsApp Business.</p>

<h2>2. Accesso</h2>
<p>L'accesso al sistema è riservato esclusivamente al personale autorizzato di Ceraldi Group S.R.L. Non è un servizio aperto al pubblico.</p>

<h2>3. Uso del Servizio WhatsApp</h2>
<p>Le notifiche WhatsApp sono inviate esclusivamente per finalità operative aziendali:</p>
<ul>
<li>Notifiche contabili giornaliere ai soci</li>
<li>Invio cedolini ai dipendenti</li>
<li>Comunicazioni HR e scadenze</li>
</ul>

<h2>4. Limitazione di Responsabilità</h2>
<p>Il sistema è fornito "così com'è" per uso interno aziendale. Ceraldi Group S.R.L. non è responsabile per eventuali interruzioni del servizio o errori nei dati.</p>

<h2>5. Proprietà</h2>
<p>Il sistema e tutti i dati in esso contenuti sono di proprietà esclusiva di Ceraldi Group S.R.L.</p>

<h2>6. Contatti</h2>
<p>Per qualsiasi questione: <strong>ceraldigroupsrl@gmail.com</strong></p>

<p><em>Ultimo aggiornamento: Aprile 2026</em></p>
</body>
</html>"""


@router.get("/api/privacy", response_class=HTMLResponse)
@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    """Informativa sulla Privacy per Meta/WhatsApp compliance."""
    return PRIVACY_HTML


@router.get("/api/terms", response_class=HTMLResponse)
@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service():
    """Condizioni d'uso per Meta/WhatsApp compliance."""
    return TERMS_HTML

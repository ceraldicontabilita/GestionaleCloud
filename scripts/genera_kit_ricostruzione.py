"""Genera il kit ZIP autosufficiente per ricostruire GestionaleCloud.

Il pacchetto contiene specifiche, mappe pagina/popup, contratti API,
configurazione senza segreti, modello dati Drive/Sheets, criteri UX e test di
accettazione. Non contiene dati aziendali, credenziali, allegati o una copia
del codice applicativo.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.genera_prompt_master import (
        PAGE_PURPOSES,
        SHEETS,
        direct_environment_names,
        parse_endpoints,
        sensitive,
        settings_variables,
        variable_group,
    )
    from scripts.rebuild_page_logic import PAGE_LOGIC, validate_page_logic
except ModuleNotFoundError:  # esecuzione diretta: python scripts/...
    from genera_prompt_master import (  # type: ignore[no-redef]
        PAGE_PURPOSES,
        SHEETS,
        direct_environment_names,
        parse_endpoints,
        sensitive,
        settings_variables,
        variable_group,
    )
    from rebuild_page_logic import PAGE_LOGIC, validate_page_logic  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "GestionaleCloud_REBUILD_KIT_2026-08-20"
TODAY = "2026-08-20"

PRIMARY_DOCS = {
    "PROMPT_MASTER.md": "01_MASTER/PROMPT_MASTER.md",
    "PRODUCT.md": "01_MASTER/PRODUCT.md",
    "DESIGN.md": "01_MASTER/DESIGN_UX.md",
    "LOGICA_FUNZIONAMENTO.md": "01_MASTER/LOGICA_FUNZIONAMENTO.md",
    "README.md": "01_MASTER/README_REPOSITORY.md",
    "CLAUDE.md": "01_MASTER/ISTRUZIONI_AGENTI.md",
    "docs/FISCAL_ACCOUNTING_POLICY.md": "02_ARCHITETTURA/POLICY_CONTABILE_FISCALE.md",
    "docs/MCP_GESTIONALE_SPEC.md": "02_ARCHITETTURA/MCP_SPEC.md",
    "docs/MCP_GESTIONALE_RUNBOOK.md": "07_TEST_E_ACCETTAZIONE/MCP_RUNBOOK.md",
    "docs/rt-locale-drive.md": "02_ARCHITETTURA/RUNTIME_LOCALE_DRIVE.md",
    "memoria/DISASTER_RECOVERY_DRIVE.md": "02_ARCHITETTURA/DISASTER_RECOVERY_DRIVE.md",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_text(base: Path, relative: str, content: str) -> Path:
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")
    return path


def write_json(base: Path, relative: str, value: Any) -> Path:
    return write_text(base, relative, json.dumps(value, ensure_ascii=False, indent=2))


def write_csv(base: Path, relative: str, rows: list[dict[str, Any]], fields: list[str]) -> Path:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return write_text(base, relative, buffer.getvalue())


def read_json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def normalize_dynamic_path(value: str) -> str:
    value = re.sub(r"\$\{[^}]+\}", "{param}", value)
    value = re.sub(r"\s+", "", value)
    return value.replace("//api/", "/api/")


def extract_frontend_logic(relative_paths: list[str]) -> dict[str, Any]:
    states: set[str] = set()
    handlers: set[str] = set()
    navigation: set[str] = set()
    imports: set[str] = set()
    api_calls: dict[tuple[str, str], set[str]] = defaultdict(set)
    verified: list[dict[str, Any]] = []

    api_pattern = re.compile(
        r"\bapi\.(get|post|put|patch|delete)\s*\(\s*([`'\"])(.{1,700}?)\2",
        flags=re.IGNORECASE | re.DOTALL,
    )
    fetch_pattern = re.compile(r"\bfetch\s*\(\s*([`'\"])(.{1,700}?)\1", re.DOTALL)
    state_pattern = re.compile(r"\bconst\s*\[\s*([A-Za-z_$][\w$]*)\s*,\s*set[A-Za-z_$][\w$]*\s*\]\s*=\s*useState")
    handler_pattern = re.compile(
        r"\b(?:const|let|function)\s+((?:handle|load|fetch|save|submit|open|close|on)[A-Z_][A-Za-z0-9_$]*)"
    )
    nav_pattern = re.compile(r"(?:navigate\s*\(|\bto\s*=\s*)\s*([`'\"])([^`'\"]+)\1")
    import_pattern = re.compile(r"^import\s+.+?\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)

    for relative in sorted(set(relative_paths)):
        path = ROOT / relative
        if not path.is_file() or path.suffix.lower() not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        verified.append(
            {
                "path": relative,
                "sha256": sha256_bytes(source.encode("utf-8")),
                "lines": len(source.splitlines()),
            }
        )
        states.update(state_pattern.findall(source))
        handlers.update(handler_pattern.findall(source))
        navigation.update(match[1] for match in nav_pattern.findall(source))
        imports.update(value for value in import_pattern.findall(source) if value.startswith(("../", "./")))
        for method, _quote, raw in api_pattern.findall(source):
            if "\n" in raw and not raw.lstrip().startswith("/"):
                continue
            endpoint = normalize_dynamic_path(raw)
            if endpoint.startswith("/api/"):
                api_calls[(method.upper(), endpoint)].add(relative)
        for _quote, raw in fetch_pattern.findall(source):
            endpoint = normalize_dynamic_path(raw)
            if endpoint.startswith("/api/"):
                api_calls[("GET", endpoint)].add(relative)

    return {
        "source_files": verified,
        "states": sorted(states),
        "handlers": sorted(handlers),
        "navigation": sorted(navigation),
        "local_imports": sorted(imports),
        "api_calls": [
            {"method": method, "path": path, "sources": sorted(sources)}
            for (method, path), sources in sorted(api_calls.items())
        ],
    }


def frontend_test_paths(page: dict[str, Any]) -> list[str]:
    component_name = Path(page["component"]).stem
    route = page["path"]
    matches: list[str] = []
    candidates = list((ROOT / "frontend/src").rglob("*.test.*")) + list((ROOT / "tests").glob("test_*.py"))
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if component_name in text or path.stem.startswith(component_name):
            matches.append(path.relative_to(ROOT).as_posix())
        elif route != "/" and f'"{route}"' in text:
            matches.append(path.relative_to(ROOT).as_posix())
    return sorted(set(matches))


def page_sources(page: dict[str, Any], page_map: dict[str, Any]) -> list[str]:
    values = {page["component"], page["entry"]}
    frontend = page_map.get("frontend") or {}
    values.update(frontend.get("file_verificati") or [])
    if frontend.get("component"):
        values.add(frontend["component"])
    if frontend.get("entry"):
        values.add(frontend["entry"])
    values.update(page_map.get("file_verificati") or [])
    return sorted(value.replace("\\", "/") for value in values if isinstance(value, str))


def render_list(values: list[str], empty: str = "Nessuno rilevato staticamente.") -> str:
    if not values:
        return empty
    return "\n".join(f"- `{value}`" for value in values)


def render_plain_list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def render_steps(values: list[str]) -> str:
    return "\n".join(f"{index}. {value}" for index, value in enumerate(values, start=1))


def render_page_document(
    page: dict[str, Any],
    page_map: dict[str, Any],
    logic: dict[str, Any],
    operating: dict[str, Any],
    endpoints: list[dict[str, str]],
    tests: list[str],
) -> str:
    by_path: dict[str, list[dict[str, str]]] = defaultdict(list)
    for endpoint in endpoints:
        by_path[endpoint["path"]].append(endpoint)

    detected = list((page_map.get("backend") or {}).get("endpoint_rilevati_nei_sorgenti") or [])
    detected.extend(page_map.get("endpoint_rilevati_nei_sorgenti") or [])
    api_rows: list[str] = []
    seen: set[tuple[str, str]] = set()
    for call in logic["api_calls"]:
        key = (call["method"], call["path"])
        seen.add(key)
        matching = [row for row in by_path.get(call["path"], []) if row["method"] == call["method"]]
        state = matching[0]["decision"] if matching else "verificare contratto dinamico"
        api_rows.append(f"- `{call['method']} {call['path']}` — `{state}` — sorgente: {', '.join(call['sources'])}")
    for path in sorted(set(detected)):
        for endpoint in by_path.get(path, []):
            key = (endpoint["method"], endpoint["path"])
            if key in seen:
                continue
            seen.add(key)
            api_rows.append(
                f"- `{endpoint['method']} {endpoint['path']}` — `{endpoint['decision']}` — {endpoint['reason']}"
            )
        if not by_path.get(path):
            api_rows.append(f"- `{path}` — endpoint rilevato nella mappa; metodo/contratto da verificare")

    source_rows = [f"{item['path']} — SHA-256 `{item['sha256']}` — {item['lines']} righe" for item in logic["source_files"]]
    purpose = PAGE_PURPOSES[page["id"]]
    map_name = Path(page["documentation_file"]).name
    return f"""# {page['id']:02d} — {page['label']}

## Contratto della schermata

- Route: `{page['path']}`
- Accesso: `{page['access']}`
- Modulo: `{page['module']}`
- Componente corrente: `{page['component']}`
- Entrypoint/router: `{page['entry']}`
- Mappa macchina: [`MAPPE_JSON/{map_name}`](MAPPE_JSON/{map_name})
- Contratto logico macchina: [`LOGICA_JSON/{page['id']:02d}-{Path(page['documentation_file']).stem}.json`](LOGICA_JSON/{page['id']:02d}-{Path(page['documentation_file']).stem}.json)
- Stato della prova corrente: `{page['audit_status']}`; una mappa statica o HTTP 200 non sono prova end-to-end.

## Scopo da preservare

{purpose}

## Fonti e registri letti

{render_plain_list(operating['sources'])}

## Scritture ed effetti consentiti

{render_plain_list(operating['writes'])}

Ogni effetto passa dal servizio/writer canonico del dominio, usa idempotency key
e conserva `canonical_id`, `operation_id`, fonte, attore e audit prima/dopo.

## Logica operativa specifica

{render_steps(operating['flow'])}

## Automazioni previste

{render_plain_list(operating['automations'])}

Le automazioni ordinarie non richiedono una plancia di pulsanti. Un errore deve
creare un caso visibile e ripetibile; non deve duplicare dati o mascherarsi da
esito riuscito.

## Collegamenti con le altre pagine

{render_plain_list(operating['links'])}

I collegamenti sono reciproci: se A mostra B, B deve mostrare A usando la stessa
`relation_id`/`operation_id` e deve aprire il record esatto, non una ricerca generica.

## Divieti e protezioni specifiche

{render_plain_list(operating['guards'])}

## Regole comuni obbligatorie

1. Caricare identità, autorizzazioni e anno globale prima dei dati di dominio.
2. Leggere i registri Drive/Sheets tramite servizi/API canonici; mai interrogare file o archivi paralleli dalla UI.
3. Mostrare caricamento, errore reale, vuoto utile e dati popolati senza trasformare errori in zero.
4. Eseguire azioni idempotenti; le associazioni certe sono automatiche, quelle ambigue mostrano candidati e motivazione.
5. Aggiornare tutte le viste collegate tramite `operation_id`/relazioni e rendere la navigazione bidirezionale.
6. Conservare fonte, hash, identificatore esterno, timestamp e stato di ogni prova.

## Criteri specifici di completamento

{render_plain_list(operating['acceptance'])}

Questi criteri vanno provati con test unitari, integrazione e almeno un percorso
browser end-to-end basato su fixture documentali verificabili.

## API rilevate dalla pagina e dalle sue mappe

{chr(10).join(api_rows) if api_rows else 'Nessuna chiamata API rilevata staticamente: verificare se la pagina è puramente di navigazione.'}

## Stato e azioni UI rilevati

### Stato locale

{render_list(logic['states'])}

### Handler e operazioni

{render_list(logic['handlers'])}

### Destinazioni di navigazione

{render_list(logic['navigation'])}

### Componenti/import locali

{render_list(logic['local_imports'])}

## Fonti tecniche verificate

{render_list(source_rows)}

## Test collegati

{render_list(tests, 'Nessun test nominale rilevato: nella riscrittura aggiungere test unitario, integrazione e browser E2E.')}

## Usabilità non negoziabile

- Una sola azione primaria per compito; niente plance di manutenzione nell'interfaccia ordinaria.
- Liste per giorno o contesto, filtri persistenti, contatori cliccabili che aprono sempre il dettaglio.
- Modali sopra il contenuto, chiusura visibile, `Esc`, focus intrappolato e ripristinato, layout responsive.
- Pulsanti tecnici solo in area amministrativa; gli ingest ordinari avvengono automaticamente.
- Ogni alert espone l'elenco dei record, il motivo, la fonte e il collegamento alla correzione.

## Criteri di accettazione della pagina

- Route e autorizzazione corrette; nessun fallback a una pagina diversa.
- Dati, conteggi, centesimi, segni, anno e saldi coerenti con i registri canonici.
- Stato visibile in tutte le sezioni interconnesse dopo refresh.
- Seconda importazione identica: `nuovi=0`, nessun duplicato o scrittura aggiuntiva.
- Ambiguità non applicate definitivamente; scelta manuale tracciata.
- Test: caricamento, errore, vuoto, popolato, permessi, mobile/desktop e almeno un flusso end-to-end reale in sola lettura.
"""


def render_architecture() -> str:
    return """# Architettura pulita da ricostruire

## Obiettivo

Un monolite modulare semplice: frontend React, API FastAPI, servizi di dominio,
adapter per Gmail/Drive/provider e archivio operativo Drive/Google Sheets. Ogni
funzione ha un solo writer canonico e un solo contratto pubblico.

```text
Fonti esterne (Gmail, Drive, banche, POS, PayPal, PagoPA)
        ↓ ingest idempotente + hash + source_external_id
Originali immutabili Drive
        ↓ parser versionato
Registri Google Sheets/Excel + entity_relations
        ↓ servizi di dominio / writer contabile unico
API autenticate e versionate
        ↓
65 pagine semplici + popup accessibili + audit/notifiche
```

## Confini

- UI: presentazione, filtri, conferme e scelta dei candidati; niente regole contabili duplicate.
- Router: validazione, auth/RBAC e contratto HTTP; niente query dirette sparse.
- Servizi: regole di dominio, idempotenza, matching e scritture atomiche.
- Adapter: Gmail, Drive, provider e fogli; retry, rate limit, watermark e lock.
- Archivio: originali su Drive; registri e indici su Sheets/Excel; nessun MongoDB nel target.
- Osservabilità: `run_id`, contatori, errori strutturati, durata, watermark e audit trail.

## Regole di dipendenza

Frontend → API → servizi → repository/adapter. Sono vietati bypass, doppie
pipeline e import che scrivono direttamente in registri contabili.
"""


def render_data_model() -> str:
    rows = "\n".join(f"| {title} | `{logical}` | `{prefix}` |" for title, logical, prefix in SHEETS)
    return f"""# Modello dati Drive/Sheets

Ogni foglio usa progressivo stabile, `canonical_id` e `operation_id`. Gli
originali restano in Drive; nei fogli si conservano metadati, relazioni e
payload JSON versionato.

| Dominio | Foglio logico | Prefisso |
|---|---|---|
{rows}

## Colonne minime comuni

`progressivo, canonical_id, operation_id, data, anno, tipo, importo, valuta,
descrizione, stato, documento_id, fattura_id, movimento_bancario_id, source,
source_external_id, file_hash, parser_version, payload_schema_version,
payload_json, created_at, updated_at`

## Identità e relazioni

- `canonical_id`: chiave deterministica dell'entità, mai riciclata.
- `operation_id`: collega prove diverse dello stesso evento senza fonderle.
- `relation_id`: relazione bidirezionale con tipo, regola, confidenza, stato e validatore.
- importi in centesimi/Decimal, valuta e segno espliciti; date ISO-8601 con timezone.
- chiavi uniche su fonte + external ID e su hash quando identifica davvero lo stesso originale.

## Prove distinte

Fattura, email, allegato, quietanza, disposizione, transazione provider,
movimento bancario e scrittura contabile restano record distinti. Una prova
documentale non certifica da sola il pagamento bancario.
"""


def render_gmail_drive() -> str:
    return """# Gmail e Drive — flusso completo

## Gmail

1. Ricerca `in:anywhere`, paginazione completa, alias mittente e wrapper PEC.
2. Conserva Gmail message ID, thread ID, Message-ID RFC, etichette, mittente,
   destinatari, data, oggetto, corpo, raw EML quando autorizzato e allegati.
3. SHA-256 su ogni allegato; doppio ingest idempotente.
4. Scheduler `Europe/Rome`, lock distribuito, watermark e retry con backoff.
5. Non spostare, eliminare, segnare come letta o alterare l'email originale.
6. PartenoPay: targa + data/ora + storico assegnazione; mai importo da solo.
7. Ambiguità: `Scegli driver`, `Scegli verbale`, `Scegli fattura`.

## Drive

1. Originali immutabili nelle cartelle canoniche.
2. Indice per Drive file ID, nome, MIME, dimensione, MD5 disponibile, SHA-256
   calcolato, percorso/provenienza e permessi.
3. Duplicato solo con hash binario esatto; nome o dimensione non bastano.
4. Nessuna pulizia senza anteprima, `canTrash`, target esatti e autorizzazione.
5. Cestino recuperabile, mai eliminazione permanente automatica.
6. Folder ID e credenziali stanno nella configurazione, non nel codice nuovo.

## Cartelle minime

`REGISTRO DATI`, `PARTENOPAY`, `CODICI TRIBUTO`, `QUIETANZE`, `DICHIARAZIONI`.
Gli alias effettivi sono in `06_CONFIG/DRIVE_FOLDERS.json`.
"""


def render_security() -> str:
    return """# Sicurezza, divieti e confini operativi

- Auth fail-closed, cookie sicuri, CSRF quando necessario, RBAC per ruolo e
  rate limit; endpoint amministrativi mai accessibili per semplice login.
- Segreti soltanto nel secret store; log, ZIP, fogli e API non li restituiscono.
- Non eseguire pagamenti automatici.
- Non eliminare/spostare email o documenti originali senza conferma esplicita.
- Non applicare associazioni definitive quando identità o provenienza sono ambigue.
- Non cancellare il backend transitorio prima della ricostruzione Drive completa.
- Non deduplicare per solo importo, data, nome file o fornitore.
- Non mostrare errori come dati zero e non dichiarare riuscito un flusso per HTTP 200.
- Ogni mutazione conserva attore, timestamp, prima/dopo, motivo e rollback.
"""


def render_migration() -> str:
    return """# Piano di migrazione e cutover

1. Congelare schemi target e chiavi canoniche.
2. Inventariare tutte le fonti e produrre conteggi, somme, hash e relazioni.
3. Creare i 22 fogli con schema/versione e vincoli unici.
4. Backfill ripetibile in sola aggiunta, con checkpoint e report errori.
5. Eseguire dual-read comparativo e poi dual-write controllato.
6. Verificare per periodo: conteggi, centesimi, saldi, documenti, relazioni e duplicati.
7. Ricostruire un ambiente vuoto usando soltanto Drive/Sheets e originali.
8. Provare scrittura/lettura, scheduler Gmail, POS/provider e navigazione bidirezionale.
9. Fermare le scritture transitorie, eseguire delta finale e cambiare runtime.
10. Monitorare, conservare rollback e disabilitare MongoDB solo dopo gate verdi.

Il cutover non autorizza eliminazione dei dati sorgente. La dismissione è una
decisione separata con backup, target esatti e prova di recupero.
"""


def render_acceptance() -> str:
    return """# Strategia di test e definizione di completato

## Per ogni pagina

- route/accesso, anno globale, loading/error/empty/populated;
- calcoli, centesimi, segni, filtri e paginazione;
- mobile, tablet, desktop, tastiera e focus;
- relazioni bidirezionali e apertura del documento originale;
- secondo ingest identico senza nuove righe;
- candidati ambigui senza mutazione definitiva.

## Per ogni endpoint

- auth/RBAC, schema request/response, errori strutturati, idempotency key;
- limite/paginazione, retry/rate limit, timeout e concorrenza;
- nessuna scrittura fuori dal servizio canonico;
- test unitario, integrazione repository/adapter e contratto OpenAPI.

## Gate di release

Backend e frontend completi, build produzione, audit statico/dead-code,
contratto MCP/OpenAPI, generatori senza diff, manifest del kit valido e CI
verde. In produzione: health con commit corretto e controlli read-only dei
flussi reali. HTTP 200 da solo non basta.
"""


def inventory_markdown_paths() -> list[str]:
    inventory = (ROOT / "docs/MARKDOWN_INVENTORY.md").read_text(encoding="utf-8")
    return re.findall(r"^\| `([^`]+\.md)` \| `(?:current|reference|generated)` \|", inventory, re.MULTILINE)


def configuration_inventory() -> list[dict[str, Any]]:
    configured = settings_variables()
    direct = direct_environment_names()
    rows: list[dict[str, Any]] = []
    for name in sorted(set(configured) | set(direct)):
        item = configured.get(name, {})
        is_secret = sensitive(name) == "segreta"
        sources = set(direct.get(name, set()))
        if item:
            sources.add(item["source"])
        rows.append(
            {
                "name": name,
                "group": variable_group(name),
                "sensitivity": sensitive(name),
                "type": item.get("type"),
                "default": None if is_secret else item.get("default"),
                "default_redacted": is_secret,
                "sources": sorted(sources),
                "target": "remove_after_verified_cutover" if variable_group(name) == "transitorie-vietate-nel-target" else "configure_if_consumed",
            }
        )
    return rows


def render_start(counts: dict[str, int], fingerprint: str) -> str:
    return f"""# START HERE — GestionaleCloud Rebuild Kit

Questo ZIP è il contratto di ricostruzione pulita di GestionaleCloud/Ceraldi ERP.
Non contiene dati reali, credenziali, allegati fiscali o una copia del vecchio codice.

## Contenuto verificato

- {counts['pages']} pagine canoniche con logica, API, stato UI, handler, fonti e test;
- {counts['page_logic_contracts']} contratti logici JSON, uno per ogni pagina;
- {counts['popups']} popup mappati;
- {counts['endpoints']} endpoint classificati, inclusi quelli in quarantena;
- {counts['variables']} variabili senza valori segreti;
- {counts['drive_folders']} alias di cartella Drive;
- {counts['sheets']} fogli/registri canonici;
- fingerprint fonti: `{fingerprint}`.

## Ordine di lettura

1. `00_PROMPT_DA_INCOLLARE.txt`
2. `01_MASTER/PROMPT_MASTER.md`
3. `02_ARCHITETTURA/`
4. `03_PAGINE/INDICE_PAGINE.md` e le 65 schede
5. `04_POPUP/INDICE_POPUP.md`
6. `05_API/ENDPOINTS.md`
7. `06_CONFIG/`
8. `07_TEST_E_ACCETTAZIONE/`
9. `MANIFEST.json` e `MANIFEST.sha256`

## Regola di autorità

Il Prompt Master è normativo. Le schede pagina e gli inventari macchina sono
completezza tecnica. I riferimenti di contesto sono subordinati e non devono
reintrodurre pipeline, endpoint o persistenze in quarantena.
"""


def render_kickoff_prompt() -> str:
    return """Devi ricostruire da zero GestionaleCloud / Ceraldi ERP usando questo ZIP come specifica.

1. Verifica prima MANIFEST.json e MANIFEST.sha256.
2. Leggi 00_START_HERE.md e poi integralmente 01_MASTER/PROMPT_MASTER.md.
3. Implementa esclusivamente le 65 pagine in 03_PAGINE e gli endpoint marcati attivi in 05_API; conserva gli endpoint in quarantena solo come decision log, senza esporli.
4. Usa Google Drive per gli originali e Google Sheets/Excel collegato a Drive per i registri. MongoDB non fa parte del target.
5. Mantieni un solo writer per concetto, canonical_id, operation_id, relazioni bidirezionali, centesimi esatti, provenienza e idempotenza.
6. Gmail deve usare in:anywhere, paginazione completa, Europe/Rome, Gmail IDs e SHA-256 senza spostare o eliminare gli originali.
7. Non eseguire pagamenti, non eliminare originali e non associare definitivamente casi ambigui. Mostra candidati e scelta manuale.
8. L'interfaccia deve essere semplice: poche azioni utili, automazioni ordinarie invisibili, alert sempre espandibili in liste, modali accessibili e dati raggruppati per contesto/giorno.
9. Procedi per moduli verticali completi: schema → servizio → API → pagina → test → flusso end-to-end. Non creare pagine vuote o pulsanti senza comportamento.
10. Considera completato solo con tutti i gate di 07_TEST_E_ACCETTAZIONE e ricostruzione Drive-only verificata.

Non inventare dati, importi, credenziali, cartelle o regole. Se manca un fatto, dichiaralo e crea uno stato da verificare; non colmare il vuoto con una supposizione.
"""


def render_html_index(pages: list[dict[str, Any]], endpoints: list[dict[str, str]]) -> str:
    page_rows = []
    for page in pages:
        filename = f"03_PAGINE/{page['id']:02d}-{Path(page['documentation_file']).stem}.md"
        page_rows.append(
            f'<tr data-search="{html.escape((page["label"] + " " + page["path"] + " " + page["module"]).lower())}">'
            f'<td>{page["id"]}</td><td><a href="{html.escape(filename)}">{html.escape(page["label"])}</a></td>'
            f'<td><code>{html.escape(page["path"])}</code></td><td>{html.escape(page["module"])}</td></tr>'
        )
    endpoint_rows = []
    for endpoint in endpoints:
        state = "attivo" if endpoint["decision"] == "tenere" else f"quarantena: {endpoint['decision']}"
        search = " ".join((endpoint["method"], endpoint["path"], endpoint["router"], state, endpoint["reason"])).lower()
        endpoint_rows.append(
            f'<tr data-search="{html.escape(search)}"><td>{html.escape(state)}</td>'
            f'<td><code>{html.escape(endpoint["method"] + " " + endpoint["path"])}</code></td>'
            f'<td>{html.escape(endpoint["router"])}</td><td>{html.escape(endpoint["reason"])}</td></tr>'
        )
    return """<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GestionaleCloud Rebuild Kit</title><style>body{font:15px system-ui;margin:0;background:#f4f7fb;color:#102a43}main{max-width:1400px;margin:auto;padding:24px}h1{margin-bottom:8px}nav a{margin-right:14px}input{width:100%;padding:12px;margin:18px 0;border:1px solid #9fb3c8;border-radius:8px}table{width:100%;border-collapse:collapse;background:#fff;margin-bottom:30px}th,td{padding:9px;border-bottom:1px solid #d9e2ec;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#102a43;color:white}code{font-size:12px}a{color:#0758c9}</style></head><body><main><h1>GestionaleCloud — Rebuild Kit</h1><p>Indice navigabile di pagine ed endpoint. Aprire prima <a href="00_START_HERE.md">START HERE</a> e <a href="01_MASTER/PROMPT_MASTER.md">PROMPT MASTER</a>.</p><nav><a href="#pagine">65 pagine</a><a href="#api">API complete</a><a href="06_CONFIG/VARIABLES.json">Variabili</a><a href="MANIFEST.json">Manifest</a></nav><input id="q" type="search" placeholder="Cerca pagina, route, router, endpoint o stato"><h2 id="pagine">Pagine</h2><table><thead><tr><th>#</th><th>Pagina</th><th>Route</th><th>Modulo</th></tr></thead><tbody>""" + "".join(page_rows) + """</tbody></table><h2 id="api">Endpoint</h2><table><thead><tr><th>Stato</th><th>Endpoint</th><th>Router</th><th>Motivo</th></tr></thead><tbody>""" + "".join(endpoint_rows) + """</tbody></table></main><script>const q=document.getElementById('q');q.addEventListener('input',()=>{const v=q.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.dataset.search.includes(v));});</script></body></html>"""


def source_fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(set(paths), key=lambda value: value.as_posix()):
        if not path.is_file():
            continue
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_package(package_root: Path) -> dict[str, Any]:
    validate_page_logic()
    catalog = read_json("page_catalog.json")
    pages = sorted(catalog["pages"], key=lambda item: item["id"])
    if len(pages) != 65 or [page["id"] for page in pages] != list(range(1, 66)):
        raise RuntimeError("Il catalogo non contiene esattamente le 65 pagine canoniche")

    endpoints = parse_endpoints()
    variables = configuration_inventory()
    drive_folders = [row for row in variables if ("DRIVE" in row["name"] or "GDRIVE" in row["name"]) and "FOLDER" in row["name"]]
    popup_paths = sorted((ROOT / "memoria/popup").glob("*.json"))
    canonical_maps = {page["documentation_file"] for page in pages}
    all_page_maps = {path.relative_to(ROOT).as_posix() for path in (ROOT / "memoria/pagine").glob("*.json")}
    quarantined_maps = sorted(all_page_maps - canonical_maps)

    fingerprint_inputs = [ROOT / "PROMPT_MASTER.md", ROOT / "page_catalog.json", ROOT / "app/config.py", ROOT / "render.yaml"]
    fingerprint_inputs.append(ROOT / "scripts/rebuild_page_logic.py")
    fingerprint_inputs.extend(ROOT / page["component"] for page in pages)
    fingerprint_inputs.extend(ROOT / path for path in canonical_maps)
    fingerprint = source_fingerprint(fingerprint_inputs)

    counts = {
        "pages": len(pages),
        "page_logic_contracts": len(PAGE_LOGIC),
        "popups": len(popup_paths),
        "endpoints": len(endpoints),
        "variables": len(variables),
        "drive_folders": len(drive_folders),
        "sheets": len(SHEETS),
        "quarantined_page_maps": len(quarantined_maps),
    }
    write_text(package_root, "00_START_HERE.md", render_start(counts, fingerprint))
    write_text(package_root, "00_PROMPT_DA_INCOLLARE.txt", render_kickoff_prompt())

    copied_sources: set[str] = set()
    for source, destination in PRIMARY_DOCS.items():
        write_text(package_root, destination, (ROOT / source).read_text(encoding="utf-8"))
        copied_sources.add(source)

    write_text(package_root, "02_ARCHITETTURA/ARCHITETTURA.md", render_architecture())
    write_text(package_root, "02_ARCHITETTURA/MODELLO_DATI_DRIVE_SHEETS.md", render_data_model())
    write_text(package_root, "02_ARCHITETTURA/GMAIL_DRIVE.md", render_gmail_drive())
    write_text(package_root, "02_ARCHITETTURA/SICUREZZA_E_DIVIETI.md", render_security())
    write_text(package_root, "02_ARCHITETTURA/MIGRAZIONE_E_CUTOVER.md", render_migration())

    page_index: list[dict[str, Any]] = []
    for page in pages:
        page_map = read_json(page["documentation_file"])
        operating = PAGE_LOGIC[page["id"]]
        sources = page_sources(page, page_map)
        logic = extract_frontend_logic(sources)
        tests = frontend_test_paths(page)
        slug = Path(page["documentation_file"]).stem
        doc_path = f"03_PAGINE/{page['id']:02d}-{slug}.md"
        logic_path = f"03_PAGINE/LOGICA_JSON/{page['id']:02d}-{slug}.json"
        write_text(package_root, doc_path, render_page_document(page, page_map, logic, operating, endpoints, tests))
        write_json(
            package_root,
            logic_path,
            {
                "schema_version": 1,
                "page_id": page["id"],
                "label": page["label"],
                "route": page["path"],
                "purpose": PAGE_PURPOSES[page["id"]],
                **operating,
            },
        )
        raw_map_destination = f"03_PAGINE/MAPPE_JSON/{Path(page['documentation_file']).name}"
        write_json(package_root, raw_map_destination, page_map)
        page_index.append(
            {
                "id": page["id"],
                "label": page["label"],
                "path": page["path"],
                "module": page["module"],
                "access": page["access"],
                "document": doc_path,
                "logic": logic_path,
                "map": raw_map_destination,
                "component": page["component"],
                "source_sha256": sha256_file(ROOT / page["component"]),
                "api_calls": len(logic["api_calls"]),
                "tests": tests,
            }
        )

    page_md = [
        "# Indice delle 65 pagine",
        "",
        "Ogni pagina ha una scheda Markdown leggibile e un contratto JSON macchina con la stessa logica.",
        "",
        "| # | Pagina | Route | Modulo | Accesso | Scheda | JSON |",
        "|---:|---|---|---|---|---|---|",
    ]
    page_md.extend(
        f"| {row['id']} | {row['label']} | `{row['path']}` | `{row['module']}` | `{row['access']}` | [{Path(row['document']).name}]({Path(row['document']).name}) | [{Path(row['logic']).name}](LOGICA_JSON/{Path(row['logic']).name}) |"
        for row in page_index
    )
    write_text(package_root, "03_PAGINE/INDICE_PAGINE.md", "\n".join(page_md))
    write_json(package_root, "03_PAGINE/INDICE_PAGINE.json", page_index)
    write_csv(package_root, "03_PAGINE/INDICE_PAGINE.csv", page_index, ["id", "label", "path", "module", "access", "document", "logic", "map", "component", "source_sha256", "api_calls"])
    for relative in quarantined_maps:
        write_json(package_root, f"03_PAGINE/QUARANTENA_MAPPE/{Path(relative).name}", read_json(relative))
    write_text(
        package_root,
        "03_PAGINE/QUARANTENA_MAPPE/README.md",
        "# Mappe fuori catalogo\n\nQueste mappe non appartengono alle 65 pagine canoniche. Servono soltanto come decision log e non autorizzano la creazione di nuove pagine.",
    )

    popup_index: list[dict[str, Any]] = []
    for path in popup_paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        destination = f"04_POPUP/MAPPE_JSON/{path.name}"
        write_json(package_root, destination, value)
        popup_index.append(
            {
                "id": path.stem,
                "popup": value.get("popup"),
                "purpose": value.get("scopo"),
                "opened_by": value.get("aperto_da") or [],
                "source_files": value.get("file_verificati") or [],
                "endpoints": value.get("endpoint_rilevati_nei_sorgenti") or [],
                "ux_rules": value.get("regole_ux") or [],
                "map": destination,
            }
        )
    popup_md = ["# Indice popup e modali", "", "Ogni popup deve avere chiusura visibile, tastiera/focus corretti e conferma per mutazioni definitive.", ""]
    popup_md.extend(f"- **{item['popup']}** — [`{item['id']}.json`](MAPPE_JSON/{item['id']}.json)" for item in popup_index)
    write_text(package_root, "04_POPUP/INDICE_POPUP.md", "\n".join(popup_md))
    write_json(package_root, "04_POPUP/INDICE_POPUP.json", popup_index)

    endpoint_rows = [
        {
            **endpoint,
            "state": "active" if endpoint["decision"] == "tenere" else "quarantine",
        }
        for endpoint in sorted(endpoints, key=lambda row: (row["router"], row["path"], row["method"]))
    ]
    write_json(package_root, "05_API/ENDPOINTS.json", endpoint_rows)
    write_csv(package_root, "05_API/ENDPOINTS.csv", endpoint_rows, ["state", "decision", "method", "path", "router", "reason"])
    api_md = ["# Tutti gli endpoint", "", "Implementare solo `active`; conservare `quarantine` come decision log.", ""]
    current_router = None
    for row in endpoint_rows:
        if row["router"] != current_router:
            current_router = row["router"]
            api_md.extend([f"## `{current_router}`", ""])
        api_md.append(f"- **{row['state']} / {row['decision']}** — `{row['method']} {row['path']}` — {row['reason']}")
    write_text(package_root, "05_API/ENDPOINTS.md", "\n".join(api_md))

    write_json(package_root, "06_CONFIG/VARIABLES.json", variables)
    write_csv(package_root, "06_CONFIG/VARIABLES.csv", variables, ["name", "group", "sensitivity", "type", "default", "default_redacted", "target"])
    env_lines = ["# Solo nomi: valorizzare nel secret/config store. Nessun segreto è incluso."]
    for item in variables:
        env_lines.extend([f"# gruppo={item['group']} target={item['target']} sensibilita={item['sensitivity']}", f"{item['name']}="])
    write_text(package_root, "06_CONFIG/ENV_TEMPLATE.example", "\n".join(env_lines))
    write_json(package_root, "06_CONFIG/DRIVE_FOLDERS.json", drive_folders)
    folder_md = ["# Alias cartelle Drive", "", "| Variabile | Default non segreto | Sorgenti |", "|---|---|---|"]
    for item in drive_folders:
        default = item["default"] if item["default"] is not None else "da configurare"
        folder_md.append(f"| `{item['name']}` | `{default}` | {', '.join(item['sources'])} |")
    write_text(package_root, "06_CONFIG/DRIVE_FOLDERS.md", "\n".join(folder_md))

    write_text(package_root, "07_TEST_E_ACCETTAZIONE/MATRICE_ACCETTAZIONE.md", render_acceptance())
    write_json(
        package_root,
        "09_MACHINE_READABLE/RECONSTRUCTION_SPEC.json",
        {
            "schema_version": 1,
            "application": "GestionaleCloud - Ceraldi ERP",
            "generated_at": TODAY,
            "source_fingerprint": fingerprint,
            "counts": counts,
            "storage_target": "google_drive_sheets",
            "canonical_pages": [row["path"] for row in page_index],
            "active_endpoints": sum(1 for row in endpoint_rows if row["state"] == "active"),
            "quarantined_endpoints": sum(1 for row in endpoint_rows if row["state"] == "quarantine"),
        },
    )
    write_json(package_root, "09_MACHINE_READABLE/page_catalog.json", catalog)

    context_intro = """# Riferimenti correnti e di contesto

Questi documenti completano il dominio ma non prevalgono sul Prompt Master.
Le descrizioni di implementazioni transitorie servono a evitare regressioni,
non autorizzano a ricreare MongoDB, pipeline duplicate o endpoint in quarantena.
"""
    write_text(package_root, "08_RIFERIMENTI_CONTESTO/README.md", context_intro)
    for relative in inventory_markdown_paths():
        if relative in copied_sources or not (ROOT / relative).is_file():
            continue
        destination = f"08_RIFERIMENTI_CONTESTO/{relative}"
        write_text(package_root, destination, (ROOT / relative).read_text(encoding="utf-8"))

    write_text(package_root, "INDEX.html", render_html_index(pages, endpoints))
    write_text(
        package_root,
        "INTEGRITY.md",
        "# Verifica integrità\n\n1. Controllare che lo ZIP si apra senza errori.\n2. Verificare SHA-256 dei file con `MANIFEST.sha256`.\n3. Confrontare conteggi con `MANIFEST.json`.\n4. Nessun file fuori dalla cartella radice del kit è ammesso.",
    )

    manifest_files = []
    for path in sorted(package_root.rglob("*")):
        if not path.is_file() or path.name in {"MANIFEST.json", "MANIFEST.sha256"}:
            continue
        manifest_files.append(
            {
                "path": path.relative_to(package_root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "schema_version": 1,
        "application": "GestionaleCloud - Ceraldi ERP",
        "generated_at": TODAY,
        "source_fingerprint": fingerprint,
        "counts": counts,
        "files": manifest_files,
    }
    write_json(package_root, "MANIFEST.json", manifest)
    hash_paths = [path for path in sorted(package_root.rglob("*")) if path.is_file() and path.name != "MANIFEST.sha256"]
    hashes = [f"{sha256_file(path)}  {path.relative_to(package_root).as_posix()}" for path in hash_paths]
    write_text(package_root, "MANIFEST.sha256", "\n".join(hashes))
    return manifest


def validate_package(package_root: Path, manifest: dict[str, Any]) -> None:
    for item in manifest["files"]:
        path = package_root / item["path"]
        if not path.is_file() or path.stat().st_size != item["size"] or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"Manifest non valido: {item['path']}")
    if len(list((package_root / "03_PAGINE").glob("[0-9][0-9]-*.md"))) != 65:
        raise RuntimeError("Numero schede pagina diverso da 65")
    if len(list((package_root / "03_PAGINE/LOGICA_JSON").glob("[0-9][0-9]-*.json"))) != 65:
        raise RuntimeError("Numero contratti logici pagina diverso da 65")
    if len(list((package_root / "04_POPUP/MAPPE_JSON").glob("*.json"))) != 36:
        raise RuntimeError("Numero mappe popup diverso da 36")
    endpoints = json.loads((package_root / "05_API/ENDPOINTS.json").read_text(encoding="utf-8"))
    if len(endpoints) != 1140:
        raise RuntimeError("Superficie endpoint incompleta")
    content = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in package_root.rglob("*") if path.is_file())
    forbidden = [
        re.compile(r"ghp_[A-Za-z0-9]{20,}"),
        re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ]
    if any(pattern.search(content) for pattern in forbidden):
        raise RuntimeError("Il kit contiene una firma compatibile con una credenziale")


def write_deterministic_zip(package_root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(package_root.rglob("*")):
            if not path.is_file():
                continue
            relative = f"{package_root.name}/{path.relative_to(package_root).as_posix()}"
            info = zipfile.ZipInfo(relative, date_time=(2026, 8, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def generate(output: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="gestionalecloud-rebuild-") as temporary:
        package_root = Path(temporary) / PACKAGE_NAME
        package_root.mkdir()
        manifest = build_package(package_root)
        validate_package(package_root, manifest)
        write_deterministic_zip(package_root, output)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP corrotto")
        top_levels = {name.split("/", 1)[0] for name in archive.namelist()}
        if top_levels != {PACKAGE_NAME}:
            raise RuntimeError("Lo ZIP non ha una sola cartella radice")
    digest = sha256_file(output)
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return {"output": str(output), "sha256": digest, "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / "Documents" / f"{PACKAGE_NAME}.zip",
        help="Percorso ZIP di destinazione",
    )
    args = parser.parse_args()
    result = generate(args.output.resolve())
    counts = result["manifest"]["counts"]
    print(
        f"ZIP: {result['output']}\nSHA-256: {result['sha256']}\n"
        f"Pagine: {counts['pages']}; popup: {counts['popups']}; endpoint: {counts['endpoints']}; "
        f"variabili: {counts['variables']}; cartelle Drive: {counts['drive_folders']}"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Agente di stampa di Lotti, sul PC del negozio.

Perché esiste: il browser non sceglie la stampante da solo e Render non
raggiunge le stampanti della rete del locale. L'agente entra col PIN di un
operatore dedicato (Impostazioni > Personale, per esempio «Stampa»), preleva i
lavori dalla coda di Lotti (``/lotti/api/stampanti/coda/pendenti``) e li manda
alla stampante Windows mappata alla categoria del documento, oppure in ESC/POS
diretto a una stampante di rete (porta 9100).

Regole:
  - il token va **solo** nell'intestazione ``Authorization``, mai nell'URL
    (il backend non legge piu' ``?token=``);
  - il token si manda solo al backend di Lotti: un lavoro con un URL di un
    altro dominio viene rifiutato, non riceve la credenziale;
  - se il token scade durante un lavoro, l'agente rientra col PIN e riprova una
    volta sola;
  - il backend e' ``https://gestionalecloud.onrender.com/lotti``. Una vecchia
    configurazione che punta al backend Render separato di Lotti (sito spento)
    viene corretta all'avvio, con un avviso.

Installazione (Windows):
  1. Python 3.9+ e SumatraPDF (stampa silenziosa dei PDF; nel PATH oppure in
     ``sumatra_path``). Per i documenti HTML serve Chrome o Edge.
  2. Copia ``print_agent_config.example.json`` in ``print_agent_config.json``
     accanto a questo file e compila stampanti e reparto.
  3. Il PIN dell'operatore di stampa va nella variabile d'ambiente
     ``LOTTI_PRINT_AGENT_PIN`` (``setx LOTTI_PRINT_AGENT_PIN 123456``), non nel
     file: ``pin`` nel file resta solo come ripiego per le installazioni vecchie.
  4. Avvio: ``python print_agent.py`` (per l'avvio automatico, un collegamento
     in ``shell:startup``).

Verifica: stampa qualcosa da Lotti; nella finestra compaiono «→ stampo …» e
«[OK] stampato», e in Impostazioni > Stampanti lo storico della coda mostra
l'esito di ogni lavoro.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

QUI = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(QUI, "print_agent_config.json")

BACKEND_PREDEFINITO = "https://gestionalecloud.onrender.com/lotti"
HOST_VIVO = "gestionalecloud.onrender.com"
HOSTS_SERVIZIO = {HOST_VIVO, "impresasemplice.online"}
VARIABILE_PIN = "LOTTI_PRINT_AGENT_PIN"


def normalizza_backend(url: str) -> str:
    """Indirizzo di Lotti a cui si accodano ``/api/...``.

    Un host spento diventa il servizio vivo; il servizio vivo senza ``/lotti``
    lo riceve, perche' Lotti e' montato li' dentro."""
    url = (url or "").strip().rstrip("/") or BACKEND_PREDEFINITO
    parti = urlsplit(url)
    # Su Render l'unico servizio vivo e' il gestionale: ogni altro host
    # *.onrender.com (i vecchi backend e frontend separati di Lotti) e' spento,
    # e una configurazione che lo nomina non stamperebbe mai nulla.
    host = parti.hostname or ""
    if host.endswith(".onrender.com") and host != HOST_VIVO:
        print(f"[AVVISO] {host} e' spento: uso {BACKEND_PREDEFINITO}")
        return BACKEND_PREDEFINITO
    if parti.scheme != "https":
        raise ValueError(f"backend_url deve essere https: {url}")
    if not parti.path.rstrip("/").endswith("/lotti"):
        url = url + "/lotti"
    return url


def leggi_pin(cfg: dict) -> str:
    pin = (os.environ.get(VARIABILE_PIN) or str(cfg.get("pin") or "")).strip()
    if not pin or pin.startswith("INSERISCI"):
        raise SystemExit(f"[ERRORE] Manca il PIN: imposta la variabile d'ambiente {VARIABILE_PIN}")
    return pin


def carica_config(percorso: str = CONFIG_PATH) -> dict:
    if not os.path.exists(percorso):
        print(f"[ERRORE] Manca {percorso}. Copia print_agent_config.example.json e compila.")
        sys.exit(1)
    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


class TokenRifiutato(Exception):
    """Il backend ha risposto 401/403: serve un nuovo login."""


class PinRifiutato(Exception):
    """Il PIN dell'agente non e' valido: non va ritentato in ciclo."""


class Sessione:
    """Login col PIN e chiamate autenticate, token solo nell'intestazione."""

    def __init__(self, backend: str, pin: str):
        self.backend = backend
        self.pin = pin
        self.host = urlsplit(backend).hostname
        self.token = ""

    def login(self) -> None:
        try:
            res = self._richiesta(
                "POST",
                f"{self.backend}/api/tablet-operatori/login",
                body={"pin": self.pin},
                autenticata=False,
            )
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                raise PinRifiutato(
                    "PIN errato, operatore non abilitato o accesso temporaneamente bloccato"
                ) from e
            raise
        dati = json.loads(res.decode() or "{}")
        if not dati.get("token"):
            raise PinRifiutato("PIN errato o operatore non abilitato")
        self.token = dati["token"]
        print(f"[OK] Login come {dati.get('operatore', {}).get('nome', '?')}")

    def verifica_url(self, url: str) -> str:
        """URL sicuro a cui mandare il token: solo il backend di Lotti, solo https.

        Il backend compone l'URL del lavoro da ``request.base_url``, che dietro
        il proxy di Render puo' arrivare ``http://``: sullo stesso host si passa
        a https, cosi' il token non viaggia mai in chiaro. Un percorso relativo
        (``/lotti/api/...``) si completa col backend."""
        testo = (url or "").strip()
        if testo.startswith("/") and not testo.startswith("//"):
            b = urlsplit(self.backend)
            testo = f"{b.scheme}://{b.netloc}{testo}"
        parti = urlsplit(testo)
        stesso_servizio = self.host in HOSTS_SERVIZIO and parti.hostname in HOSTS_SERVIZIO
        if parti.scheme not in ("http", "https") or (parti.hostname != self.host and not stesso_servizio):
            raise ValueError(f"URL del documento fuori dal backend di Lotti: {parti.hostname or url!r}")
        if "token=" in (parti.query or ""):
            raise ValueError("URL del documento con un token in query: rifiutato")
        return parti._replace(scheme="https").geturl()

    def _richiesta(self, metodo: str, url: str, body: dict | None = None, autenticata: bool = True,
                   timeout: int = 30) -> bytes:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=metodo)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if autenticata and self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if autenticata and e.code in (401, 403):
                raise TokenRifiutato(f"HTTP {e.code}") from e
            raise

    def chiama(self, metodo: str, url: str, body: dict | None = None, timeout: int = 30) -> bytes:
        """Chiamata autenticata: token scaduto -> nuovo login e un solo nuovo tentativo."""
        url = self.verifica_url(url)
        try:
            return self._richiesta(metodo, url, body=body, timeout=timeout)
        except TokenRifiutato:
            print("[INFO] token scaduto, nuovo login…")
            self.login()
            return self._richiesta(metodo, url, body=body, timeout=timeout)

    def json(self, metodo: str, url: str, body: dict | None = None) -> dict:
        return json.loads(self.chiama(metodo, url, body=body).decode() or "{}")


def invia_escpos(dati: bytes, ip: str, porta: int) -> None:
    """Byte ESC/POS diretti alla stampante di rete (socket RAW, di norma 9100)."""
    import socket

    with socket.create_connection((ip, int(porta or 9100)), timeout=15) as s:
        s.sendall(dati)


def trova_chrome() -> str:
    for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ):
        if os.path.exists(p):
            return p
    return ""


def html_to_pdf(html_path: str, pdf_path: str, chrome: str) -> None:
    if not chrome:
        raise RuntimeError("Chrome/Edge non trovato: impossibile convertire HTML in PDF")
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-margins",
         f"--print-to-pdf={pdf_path}", "file:///" + html_path.replace("\\", "/")],
        check=True, timeout=60,
    )


def stampa_pdf(pdf_path: str, stampante: str, sumatra: str) -> None:
    """Stampa silenziosa di un PDF sulla stampante indicata."""
    if sys.platform.startswith("win"):
        exe = sumatra or "SumatraPDF.exe"
        destinazione = ["-print-to", stampante] if stampante else ["-print-to-default"]
        subprocess.run([exe, *destinazione, "-silent", pdf_path], check=True, timeout=120)
    else:
        subprocess.run(["lp", *(["-d", stampante] if stampante else []), pdf_path], check=True, timeout=120)


def gestisci_job(job: dict, cfg: dict, chrome: str, sessione: Sessione) -> None:
    formato = (job.get("formato") or "pdf").lower()
    titolo = job.get("titolo") or job.get("categoria")

    if formato == "escpos":
        st = job.get("stampante") or {}
        ip = st.get("indirizzo_rete") or cfg.get("escpos_ip", "")
        porta = st.get("porta") or cfg.get("escpos_porta", 9100)
        if not ip:
            raise RuntimeError("ESC/POS: IP stampante non configurato (indirizzo_rete vuoto)")
        print(f"  → ESC/POS '{titolo}' diretto a {ip}:{porta}")
        invia_escpos(sessione.chiama("GET", job["url"], timeout=60), ip, porta)
        return

    stampante = job.get("stampante_windows") or cfg.get("stampante_default", "")
    print(f"  → stampo '{titolo}' ({job.get('categoria')}) su '{stampante or 'predefinita'}'")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "doc." + ("html" if formato == "html" else "pdf"))
        with open(src, "wb") as out:
            out.write(sessione.chiama("GET", job["url"], timeout=60))
        pdf = src
        if formato == "html":
            pdf = os.path.join(tmp, "doc.pdf")
            html_to_pdf(src, pdf, chrome)
        stampa_pdf(pdf, stampante, cfg.get("sumatra_path", ""))


def giro(sessione: Sessione, cfg: dict, chrome: str) -> int:
    """Un prelievo dalla coda: stampa i lavori e ne comunica l'esito."""
    reparto = cfg.get("reparto", "")
    base = sessione.backend
    res = sessione.json("GET", f"{base}/api/stampanti/coda/pendenti?reparto={reparto}")
    fatti = 0
    for job in res.get("jobs", []):
        esito_url = f"{base}/api/stampanti/coda/{job['id']}/esito"
        try:
            gestisci_job(job, cfg, chrome, sessione)
            sessione.json("POST", esito_url, body={"ok": True})
            print(f"  [OK] stampato {job['id']}")
            fatti += 1
        except Exception as e:  # un lavoro rotto non ferma la coda
            errore = f"{type(e).__name__}: {e}"
            print(f"  [ERRORE] job {job.get('id')}: {errore}")
            try:
                sessione.json("POST", esito_url, body={"ok": False, "errore": errore})
            except Exception as e2:
                print(f"  [ERRORE] esito del job {job.get('id')} non registrato: {type(e2).__name__}: {e2}")
    return fatti


def main() -> None:
    cfg = carica_config()
    sessione = Sessione(normalizza_backend(cfg.get("backend_url", "")), leggi_pin(cfg))
    intervallo = int(cfg.get("poll_secondi", 5))
    chrome = trova_chrome()
    print(f"[AVVIO] Agente di stampa Lotti — {sessione.backend}, reparto '{cfg.get('reparto') or 'tutti'}', "
          f"ogni {intervallo}s")
    try:
        sessione.login()
    except PinRifiutato as e:
        raise SystemExit(
            f"[ERRORE] {e}. L'agente si arresta per non bloccare gli accessi: "
            f"correggi {VARIABILE_PIN} e riavvialo."
        ) from e
    while True:
        try:
            giro(sessione, cfg, chrome)
        except PinRifiutato as e:
            raise SystemExit(
                f"[ERRORE] {e}. L'agente si arresta per non ripetere il PIN: "
                f"correggi {VARIABILE_PIN} e riavvialo."
            ) from e
        except urllib.error.HTTPError as e:
            print(f"[HTTP {e.code}] {e}")
        except Exception as e:
            print(f"[RETE] {type(e).__name__}: {e} — riprovo tra {intervallo}s")
        time.sleep(intervallo)


if __name__ == "__main__":
    main()

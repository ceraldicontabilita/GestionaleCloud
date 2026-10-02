"""Colazioni B&B, correzioni dell'audit del 02/10/2026: la pagina e la migrazione tengono le regole.

Prove statiche sui due artefatti (pagina unica senza build e migrazione SQL):
l'SQL vero gira sul database, qui si fissa cio' che un `grep` puo' far rispettare.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")
SQL = (ROOT / "supabase" / "migrations" / "20261002060000_colazioni_audit_02_10.sql").read_text(encoding="utf-8")
JS = HTML[HTML.index("<script>") + 8:HTML.rindex("</script>")]


def test_la_v23_sta_nel_registro_delle_migrazioni():
    v23 = (ROOT / "frontend_colazioni" / "sql" / "supabase-23.sql").read_text(encoding="utf-8")
    copia = (ROOT / "supabase" / "migrations" / "20261001120000_colazioni_bb_v23_recensioni.sql").read_text(encoding="utf-8")
    assert copia == v23


def test_csp_e_integrity_sulla_libreria_qr():
    assert '<meta http-equiv="Content-Security-Policy"' in HTML
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', HTML).group(1)
    assert "connect-src 'self' https://lohczjdiawjryuopncwc.supabase.co" in csp
    assert "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com" in csp
    assert "font-src https://fonts.gstatic.com" in csp and "https://fonts.googleapis.com" in csp
    assert "object-src 'none'" in csp
    tag = re.search(r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/qrcodejs/1\.0\.0/qrcode\.min\.js"[^>]*>', HTML).group(0)
    assert 'integrity="sha384-' in tag and 'crossorigin="anonymous"' in tag


def test_nessun_valore_passa_da_esc_dentro_un_onclick():
    # un valore interpolato in un handler inline e' codice, non testo: si usa data-* e un listener
    assert not re.findall(r'onclick="[^"]*esc\(', HTML)
    assert "recApri(\\'" not in HTML
    assert 'data-dest="google"' in HTML


def test_il_qr_del_voucher_e_il_link_ospite_e_lo_scanner_lo_capisce():
    assert "qr:linkOspite(v.id)" in JS
    assert 'qr($("#qrbox"),linkOspite(d.id))' in JS
    assert 'qr($("#qrbox"),l)' in JS  # mostraQR dell'albergatore
    assert re.search(r"match\(/#\\/ospite\\/\(\[A-Za-z0-9\]\+\)/i\)", JS)
    assert "navigator.clipboard.writeText(l)" in JS  # «Copia link per NFC» copia il link ospite
    assert 'id="nfcrec"' in JS  # il link recensioni ha un bottone suo


def test_le_liste_si_leggono_sempre_come_liste():
    assert "function gNorm(d)" in JS
    assert "Array.isArray(r.allergie)" in JS and "Array.isArray(r.modifiche)" in JS
    assert "const reqListe=" in JS and "Array.isArray(v.extra)" in JS


def test_extra_per_giorno_in_pagina():
    assert "pgiorno:G.giorno" in JS
    assert "function gSetGiorno(g)" in JS
    assert "pgiorno:TIT.oggi" in JS  # incasso del giorno dallo scanner
    assert "reqHtml(v,PDAY)" in JS  # produzione: solo gli extra del giorno
    assert "extra_pagato" not in JS


def test_annullo_albergatore_solo_entro_il_soggiorno_e_titolare_con_motivo():
    assert "fine(v)>=oggi?`<button class=\"btn sm sec\" onclick=\"annullaAlb(" in JS
    assert 'run("bb_tit_annulla",{p:sess.p,vid:id,pmotivo:m})' in JS
    assert "function scegliMotivo(" in JS
    assert "raise exception 'Soggiorno terminato: chiedi al bar'" in SQL
    assert "raise exception 'Scrivi il motivo dell''annullo'" in SQL
    assert "drop function if exists public.bb_tit_annulla(text,text);" in SQL


def test_niente_cambia_pin_del_titolare_e_niente_legacy():
    assert "nuovoPin" not in JS and "Cambia PIN</button>" not in JS.split("/* ============ TITOLARE")[1]
    assert "tavoloSet" not in JS and "bb_tit_tavolo_set" not in JS
    assert "drop function if exists public.bb_tit_struttura_salva(text,uuid,text,text,text,int[]);" in SQL
    for fn in ("bb_alb_crea_voucher", "bb_alb_crea_batch", "bb_tit_menu_set", "bb_tit_menu_import",
               "bb_tit_menu_elimina", "bb_tit_bar_set", "bb_tit_voci_salva", "bb_pin_stato", "bb_tit_tavolo_set"):
        assert f"drop function if exists public.{fn}(" in SQL
        assert fn not in JS
    assert "drop table" not in SQL.lower()


def test_disattivazione_struttura():
    assert "create or replace function public.bb_tit_struttura_disattiva(p text, sid uuid, pmotivo text)" in SQL
    assert "raise exception 'Struttura disattivata: contatta il bar'" in SQL
    assert 'run("bb_tit_struttura_disattiva",{p:sess.p,sid:id,pmotivo:m}' in JS
    assert "if(h.disattivata)" in JS


def test_ip_tentativi_codice_voucher_e_limite_ospite():
    assert "x-real-ip" in SQL and "cf-connecting-ip" in SQL
    assert "if ki is not null then perform public.bb_fallito(ki,25); end if;" in SQL
    assert "upper(substr(encode(extensions.gen_random_bytes(12),'hex'),1,16))" in SQL
    assert "k := 'ospite:'||substr(k,4);" in SQL and "if r.n >= 60 then" in SQL
    assert "perform public.bb_limite_ospite();" in SQL.split("create or replace function public.bb_ospite(vid text)")[1]
    assert "perform public.bb_limite_ospite();" in SQL.split("create or replace function public.bb_ospite_salva(")[1]


def test_richieste_validate_e_consenso_solo_con_informativa():
    assert "k not in ('allergie','nota','modifiche')" in SQL
    assert "left(coalesce(prichieste->>'nota',''),500)" in SQL
    assert "k not in ('voce','tipo','testo','chi','variante','diff')" in SQL
    assert "exists(select 1 from menu.menu_allergens al where al.id=x)" in SQL
    assert "if pacconsento and public.bb_cfg('recensioni_informativa_url','')='' then raise exception" in SQL
    assert "'Non acconsento / continua'" in JS or "Non acconsento / continua" in JS
    assert "v.fonte,public.bb_ip()" in SQL  # la fonte del consenso e' quella della visita
    assert "'pagina_colazione'" not in SQL


def test_geolocalizzazione_informativa_non_bloccante():
    assert "create or replace function public.bb_distanza_m(" in SQL
    assert "'bar_lat','bar_lon','bar_raggio_m'" in SQL
    assert "distanza_m,in_sede" in SQL
    assert 'f("bar_lat"' in JS and 'f("bar_raggio_m"' in JS
    assert "posizione non nota" in JS and "fuori sede" in JS and "in sede" in JS

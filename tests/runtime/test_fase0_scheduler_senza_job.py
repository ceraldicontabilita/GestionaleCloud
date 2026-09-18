"""Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md punti 1, 2, 4): tre automazioni
periodiche spente non devono più essere richiamate da start_scheduler().

I punti 1 e 2 erano chiamate dentro un job più grande (non un job a sé), quindi
la prova è che il modulo non le referenzia più affatto (nessun modo residuo
di invocarle dallo scheduler). Il punto 4 era un job a sé con un `id` proprio,
quindi lì la prova è la sua assenza tra i job registrati.
"""
import inspect

import app.scheduler as scheduler_mod


class _FakeScheduler:
    def __init__(self):
        self.jobs = []
        self.running = False

    def add_job(self, fn, *args, **kwargs):
        self.jobs.append((fn, args, kwargs))

    def start(self):
        self.running = True


def test_auto_conferma_provvisori_per_metodo_non_richiamato_dallo_scheduler():
    sorgente = inspect.getsource(scheduler_mod)
    assert "import auto_conferma_provvisori_per_metodo" not in sorgente
    assert "await auto_conferma_provvisori_per_metodo(" not in sorgente


def test_sposta_fatture_cassa_pagate_in_banca_non_richiamato_dallo_scheduler():
    sorgente = inspect.getsource(scheduler_mod)
    assert "import sposta_fatture_cassa_pagate_in_banca" not in sorgente
    assert "await sposta_fatture_cassa_pagate_in_banca(" not in sorgente


def test_drive_f24_quadratura_non_registrato(monkeypatch):
    scheduler = _FakeScheduler()
    monkeypatch.setattr(scheduler_mod, "scheduler", scheduler)
    scheduler_mod.start_scheduler()
    ids = {j[2].get("id") for j in scheduler.jobs if isinstance(j[2], dict)}
    assert "drive_f24_quadratura" not in ids

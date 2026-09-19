import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';
import { toast } from '../../hooks/use-toast';
import {
  AlertTriangle, CheckCircle2, ShieldOff, RotateCcw, ChevronDown, ChevronRight, Eye,
} from 'lucide-react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

// Palette del gruppo Ceraldi (CLAUDE.md): salvia su crema, semantici caldi.
const SALVIA = '#5b7a6b';
const SALVIA_SCURA = '#3f5a4e';
const CREMA = '#faf7f0';
const CARD = '#fffefb';
const SABBIA = '#e6e0d4';
const INCHIOSTRO = '#2a3329';
const AVVISO = '#c4894a';
const SUCCESSO = '#3d8168';
const PERICOLO = '#d35f4e';

// "Le mani sporche" (CLAUDE.md): il motivo si sceglie da un bottone, non si
// scrive. "Altro" resta l'eccezione, e comunque il motivo e' facoltativo.
const MOTIVI_PRONTI = [
  'Bevanda in bottiglia sigillata',
  'Distillato o liquore',
  'Nessuno dei 14 allergeni UE',
  'Prodotto non alimentare',
];

const ETICHETTA_TIPO = {
  prodotto: 'Prodotto',
  categoria: 'Categoria',
  sottocategoria: 'Sottocategoria',
};

const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('admin_token')}` },
});

/**
 * Allergeni mancanti: chi deve dichiarare gli allergeni e non lo fa.
 *
 * 19/09/2026 — "Collega a una ricetta" e' stato tolto da qui: la strada
 * ricetta -> prodotto del Menu e' quella del ponte di Lotti, che pubblica la
 * ricetta con gli allergeni gia' calcolati dagli ingredienti.
 * Al suo posto l'esclusione: whisky, distillati e bibite in bottiglia non
 * hanno allergeni da dichiarare e non devono restare nell'alert per sempre.
 * L'esclusione non nasconde nulla dal menu, e si revoca.
 */
const AllergeniMancanti = () => {
  const [dati, setDati] = useState(null);
  const [esclusioni, setEsclusioni] = useState([]);
  const [caricamento, setCaricamento] = useState(true);
  const [mostraEsclusioni, setMostraEsclusioni] = useState(false);
  const [gruppiAperti, setGruppiAperti] = useState({});
  const [richiesta, setRichiesta] = useState(null); // { tipo, riferimento_id, nome, quanti }

  const carica = async () => {
    setCaricamento(true);
    try {
      const [mancanti, escl] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/admin/allergeni/mancanti`, auth()),
        axios.get(`${BACKEND_URL}/api/admin/allergeni/esclusioni`, auth()),
      ]);
      setDati(mancanti.data);
      setEsclusioni(escl.data.esclusioni || []);
    } catch (error) {
      toast({
        title: 'Errore',
        description: 'Elenco allergeni mancanti non disponibile',
        variant: 'destructive',
      });
    }
    setCaricamento(false);
  };

  useEffect(() => { carica(); }, []);

  const escludi = async ({ tipo, riferimento_id, motivo }) => {
    try {
      await axios.post(
        `${BACKEND_URL}/api/admin/allergeni/esclusioni`,
        { tipo, riferimento_id, motivo: motivo || null },
        auth(),
      );
      toast({
        title: 'Escluso dalla verifica',
        description: 'Non richiede la dichiarazione allergeni. Puoi annullare quando vuoi.',
      });
      setRichiesta(null);
      carica();
    } catch (error) {
      toast({
        title: 'Errore',
        variant: 'destructive',
        description: error.response?.data?.detail || 'Esclusione non riuscita',
      });
    }
  };

  const revoca = async (tipo, riferimentoId) => {
    try {
      await axios.delete(
        `${BACKEND_URL}/api/admin/allergeni/esclusioni/${tipo}/${riferimentoId}`,
        auth(),
      );
      toast({
        title: 'Esclusione annullata',
        description: 'Torna nell’elenco di chi deve dichiarare gli allergeni.',
      });
      carica();
    } catch (error) {
      toast({
        title: 'Errore',
        variant: 'destructive',
        description: error.response?.data?.detail || 'Ripristino non riuscito',
      });
    }
  };

  // Raggruppamento per sottocategoria (il livello su cui il titolare ragiona:
  // "Whisky", "Bibite"), con la categoria come contesto.
  const gruppi = useMemo(() => {
    const per = new Map();
    (dati?.prodotti || []).forEach((p) => {
      const chiave = p.subcategory_id ?? `cat-${p.category_id}`;
      if (!per.has(chiave)) {
        per.set(chiave, {
          chiave,
          subcategory_id: p.subcategory_id,
          category_id: p.category_id,
          sottocategoria_nome: p.sottocategoria_nome,
          categoria_nome: p.categoria_nome,
          prodotti: [],
        });
      }
      per.get(chiave).prodotti.push(p);
    });
    return [...per.values()].sort((a, b) =>
      (a.sottocategoria_nome || '').localeCompare(b.sottocategoria_nome || ''));
  }, [dati]);

  if (caricamento) return null;
  if (!dati) return null;

  const nessunoDaDichiarare = dati.senza_allergeni === 0;

  return (
    <>
      <Card
        className="mb-6"
        style={{
          background: nessunoDaDichiarare ? CARD : CREMA,
          borderColor: nessunoDaDichiarare ? SABBIA : AVVISO,
        }}
      >
        <CardHeader className="pb-3">
          <CardTitle className="flex flex-wrap items-center gap-2 text-base sm:text-lg">
            {nessunoDaDichiarare ? (
              <span className="flex items-center gap-2" style={{ color: SUCCESSO }}>
                <CheckCircle2 className="w-5 h-5 shrink-0" />
                Tutti i prodotti hanno una dichiarazione allergeni o sono esclusi.
              </span>
            ) : (
              <span className="flex items-center gap-2" style={{ color: AVVISO }}>
                <AlertTriangle className="w-5 h-5 shrink-0" />
                {dati.senza_allergeni} prodotti senza allergeni dichiarati
              </span>
            )}
          </CardTitle>
          <p className="text-sm" style={{ color: SALVIA_SCURA }}>
            Dichiarare i 14 allergeni UE è un obbligo di legge (Reg. UE 1169/2011).
            {dati.esclusi > 0 && ` ${dati.esclusi} prodotti sono esclusi dalla verifica.`}
          </p>
          {(dati.esclusi > 0 || esclusioni.length > 0) && (
            <Button
              variant="outline"
              onClick={() => setMostraEsclusioni((v) => !v)}
              className="min-h-[44px] w-full sm:w-auto justify-start"
              style={{ borderColor: SABBIA, color: SALVIA_SCURA, background: CARD }}
            >
              <Eye className="w-4 h-4 mr-2" />
              {mostraEsclusioni ? 'Nascondi' : 'Vedi'} le {esclusioni.length} esclusioni
            </Button>
          )}
        </CardHeader>

        <CardContent className="space-y-4">
          {mostraEsclusioni && (
            <ElencoEsclusioni esclusioni={esclusioni} onRevoca={revoca} />
          )}

          {gruppi.map((g) => (
            <GruppoProdotti
              key={g.chiave}
              gruppo={g}
              aperto={gruppiAperti[g.chiave] !== false}
              onToggle={() => setGruppiAperti((s) => ({
                ...s, [g.chiave]: s[g.chiave] === false,
              }))}
              onChiediEsclusione={setRichiesta}
            />
          ))}
        </CardContent>
      </Card>

      <DialogEsclusione
        richiesta={richiesta}
        onAnnulla={() => setRichiesta(null)}
        onConferma={escludi}
      />
    </>
  );
};

const GruppoProdotti = ({ gruppo, aperto, onToggle, onChiediEsclusione }) => {
  const titolo = gruppo.sottocategoria_nome || gruppo.categoria_nome || 'Senza reparto';
  const Freccia = aperto ? ChevronDown : ChevronRight;

  return (
    <div className="rounded-lg border overflow-hidden" style={{ borderColor: SABBIA, background: CARD }}>
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 p-3" style={{ background: CREMA }}>
        <button
          type="button"
          onClick={onToggle}
          className="flex items-center gap-2 text-left min-h-[44px] flex-1"
          style={{ color: INCHIOSTRO }}
        >
          <Freccia className="w-4 h-4 shrink-0" style={{ color: SALVIA }} />
          <span className="font-semibold">{titolo}</span>
          <span className="text-xs" style={{ color: SALVIA_SCURA }}>
            {gruppo.categoria_nome ? `${gruppo.categoria_nome} · ` : ''}
            {gruppo.prodotti.length} prodotti
          </span>
        </button>
        {gruppo.subcategory_id != null && (
          <Button
            variant="outline"
            onClick={() => onChiediEsclusione({
              tipo: 'sottocategoria',
              riferimento_id: gruppo.subcategory_id,
              nome: titolo,
              quanti: gruppo.prodotti.length,
            })}
            className="min-h-[44px] w-full sm:w-auto"
            style={{ borderColor: SALVIA, color: SALVIA_SCURA, background: CARD }}
          >
            <ShieldOff className="w-4 h-4 mr-2" />
            Escludi tutto il reparto
          </Button>
        )}
      </div>

      {aperto && (
        <ul className="divide-y" style={{ borderColor: SABBIA }}>
          {gruppo.prodotti.map((p) => (
            <li
              key={p.id}
              className="p-3 flex flex-col sm:flex-row sm:items-center gap-2"
            >
              <div className="min-w-0 flex-1">
                <div className="font-medium break-words" style={{ color: INCHIOSTRO }}>
                  {p.name_it}
                </div>
                {p.description_it && (
                  <div className="text-xs break-words" style={{ color: SALVIA_SCURA }}>
                    {p.description_it}
                  </div>
                )}
                {p.visible === false && (
                  <div className="text-xs" style={{ color: AVVISO }}>Non visibile nel menu pubblico</div>
                )}
              </div>
              <Button
                variant="outline"
                onClick={() => onChiediEsclusione({
                  tipo: 'prodotto', riferimento_id: p.id, nome: p.name_it, quanti: 1,
                })}
                className="min-h-[44px] w-full sm:w-auto shrink-0"
                style={{ borderColor: SABBIA, color: SALVIA_SCURA, background: CARD }}
              >
                <ShieldOff className="w-4 h-4 mr-2" />
                Non richiede allergeni
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const ElencoEsclusioni = ({ esclusioni, onRevoca }) => {
  if (esclusioni.length === 0) {
    return (
      <p className="text-sm" style={{ color: SALVIA_SCURA }}>
        Nessuna esclusione attiva.
      </p>
    );
  }
  return (
    <div className="rounded-lg border" style={{ borderColor: SABBIA, background: CARD }}>
      <div className="p-3 text-sm font-semibold" style={{ background: CREMA, color: INCHIOSTRO }}>
        Esclusi dalla verifica allergeni
      </div>
      <ul className="divide-y" style={{ borderColor: SABBIA }}>
        {esclusioni.map((e) => (
          <li
            key={`${e.tipo}-${e.riferimento_id}`}
            className="p-3 flex flex-col sm:flex-row sm:items-center gap-2"
          >
            <div className="min-w-0 flex-1">
              <div className="font-medium break-words" style={{ color: INCHIOSTRO }}>
                {e.nome || `#${e.riferimento_id}`}
                <span className="ml-2 text-xs" style={{ color: SALVIA_SCURA }}>
                  {ETICHETTA_TIPO[e.tipo] || e.tipo}
                </span>
              </div>
              <div className="text-xs break-words" style={{ color: SALVIA_SCURA }}>
                {e.motivo || 'Nessun motivo indicato'}
              </div>
            </div>
            <Button
              variant="outline"
              onClick={() => onRevoca(e.tipo, e.riferimento_id)}
              className="min-h-[44px] w-full sm:w-auto shrink-0"
              style={{ borderColor: PERICOLO, color: PERICOLO, background: CARD }}
            >
              <RotateCcw className="w-4 h-4 mr-2" />
              Annulla esclusione
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
};

const DialogEsclusione = ({ richiesta, onAnnulla, onConferma }) => {
  const [motivo, setMotivo] = useState('');
  const [altro, setAltro] = useState(false);

  useEffect(() => {
    setMotivo('');
    setAltro(false);
  }, [richiesta]);

  if (!richiesta) return null;

  const diGruppo = richiesta.tipo !== 'prodotto';

  return (
    <Dialog open onOpenChange={(aperto) => { if (!aperto) onAnnulla(); }}>
      <DialogContent style={{ background: CARD, borderColor: SABBIA }}>
        <DialogHeader>
          <DialogTitle style={{ color: INCHIOSTRO }}>
            {diGruppo ? 'Escludere tutto il reparto?' : 'Non richiede allergeni?'}
          </DialogTitle>
          <DialogDescription style={{ color: SALVIA_SCURA }}>
            {diGruppo
              ? `"${richiesta.nome}" e i suoi ${richiesta.quanti} prodotti spariranno da questo elenco.`
              : `"${richiesta.nome}" sparirà da questo elenco.`}
            {' '}Resta nel menu come sempre: cambia solo la verifica allergeni, e puoi annullare quando vuoi.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <p className="text-sm font-medium" style={{ color: INCHIOSTRO }}>
            Motivo (facoltativo)
          </p>
          <div className="flex flex-wrap gap-2">
            {MOTIVI_PRONTI.map((m) => {
              const scelto = !altro && motivo === m;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setAltro(false); setMotivo(scelto ? '' : m); }}
                  className="min-h-[44px] px-3 rounded-md border text-sm text-left"
                  style={{
                    borderColor: scelto ? SALVIA : SABBIA,
                    background: scelto ? SALVIA : CREMA,
                    color: scelto ? CREMA : INCHIOSTRO,
                  }}
                >
                  {m}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => { setAltro(true); setMotivo(''); }}
              className="min-h-[44px] px-3 rounded-md border text-sm"
              style={{
                borderColor: altro ? SALVIA : SABBIA,
                background: altro ? SALVIA : CREMA,
                color: altro ? CREMA : INCHIOSTRO,
              }}
            >
              Altro (scrivi tu)
            </button>
          </div>
          {altro && (
            <Input
              autoFocus
              placeholder="Perché non richiede la dichiarazione allergeni"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              maxLength={200}
              className="min-h-[44px]"
              style={{ borderColor: SABBIA, background: CREMA, color: INCHIOSTRO }}
            />
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            onClick={onAnnulla}
            className="min-h-[44px] w-full sm:w-auto"
            style={{ borderColor: SABBIA, color: SALVIA_SCURA, background: CARD }}
          >
            Annulla
          </Button>
          <Button
            onClick={() => onConferma({
              tipo: richiesta.tipo,
              riferimento_id: richiesta.riferimento_id,
              motivo: motivo.trim(),
            })}
            className="min-h-[44px] w-full sm:w-auto"
            style={{ background: SALVIA, color: CREMA }}
          >
            <ShieldOff className="w-4 h-4 mr-2" />
            Conferma esclusione
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default AllergeniMancanti;

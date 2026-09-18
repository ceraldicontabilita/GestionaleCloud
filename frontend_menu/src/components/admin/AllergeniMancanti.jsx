import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { toast } from '../../hooks/use-toast';
import { AlertTriangle, Link2, RefreshCw, CheckCircle2 } from 'lucide-react';
import axios from 'axios';
import { allergensList } from '../../mockData';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const nomeAllergeni = (ids) =>
  (ids || [])
    .map((id) => allergensList.find((a) => a.id === id)?.nameIT || id)
    .join(', ');

// 18/09/2026: niente abbinamento automatico per somiglianza di nome tra un
// prodotto del Menu e una ricetta di Lotti — provato e scartato, produce
// accoppiamenti sbagliati (es. spritz diversi sulla stessa ricetta generica).
// Qui la persona sceglie la ricetta giusta una volta; da quel momento il
// sistema tiene sincronizzati gli allergeni da solo (pulsante "Risincronizza").
const AllergeniMancanti = () => {
  const [dati, setDati] = useState(null);
  const [ricette, setRicette] = useState([]);
  const [ricetteDisponibili, setRicetteDisponibili] = useState(true);
  const [caricamento, setCaricamento] = useState(true);
  const [ricercaPerProdotto, setRicercaPerProdotto] = useState({});
  const [risincronizzando, setRisincronizzando] = useState(false);

  const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('admin_token')}` } });

  const carica = async () => {
    setCaricamento(true);
    try {
      const { data } = await axios.get(`${BACKEND_URL}/api/admin/allergeni/mancanti`, auth());
      setDati(data);
    } catch (error) {
      toast({ title: 'Errore', description: 'Elenco allergeni mancanti non disponibile', variant: 'destructive' });
    }
    try {
      const { data } = await axios.get(`${BACKEND_URL}/api/admin/allergeni/ricette-lotti`, auth());
      setRicette(data.ricette || []);
      setRicetteDisponibili(true);
    } catch (error) {
      setRicetteDisponibili(false);
    }
    setCaricamento(false);
  };

  useEffect(() => { carica(); }, []);

  const associa = async (productId, ricettaDocId, nomeRicetta) => {
    try {
      await axios.post(`${BACKEND_URL}/api/admin/allergeni/associa`,
        { product_id: productId, ricetta_doc_id: ricettaDocId }, auth());
      toast({ title: 'Associato', description: `Allergeni copiati dalla ricetta "${nomeRicetta}"` });
      carica();
    } catch (error) {
      toast({
        title: 'Errore', variant: 'destructive',
        description: error.response?.data?.detail || 'Associazione non riuscita',
      });
    }
  };

  const risincronizza = async () => {
    setRisincronizzando(true);
    try {
      const { data } = await axios.post(`${BACKEND_URL}/api/admin/allergeni/risincronizza`, {}, auth());
      toast({
        title: 'Risincronizzato',
        description: data.totale_aggiornati > 0
          ? `${data.totale_aggiornati} prodotti riallineati alla loro ricetta Lotti`
          : 'Tutti i prodotti collegati erano gia\' allineati',
      });
      carica();
    } catch (error) {
      toast({ title: 'Errore', description: 'Risincronizzazione non riuscita', variant: 'destructive' });
    }
    setRisincronizzando(false);
  };

  if (caricamento) return null;
  if (!dati || dati.senza_allergeni === 0) {
    return (
      <Card className="border-green-200 bg-green-50">
        <CardContent className="py-4 flex items-center gap-2 text-green-700">
          <CheckCircle2 className="w-5 h-5" />
          <span>Tutti i prodotti visibili hanno una dichiarazione allergeni.</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-amber-300 bg-amber-50 mb-6">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-amber-800">
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" />
            {dati.senza_allergeni} prodotti senza allergeni dichiarati
            {dati.senza_ricetta_collegata > 0 && ` (${dati.senza_ricetta_collegata} senza ricetta collegata)`}
          </span>
          <Button size="sm" variant="outline" onClick={risincronizza} disabled={risincronizzando}>
            <RefreshCw className={`w-4 h-4 mr-2 ${risincronizzando ? 'animate-spin' : ''}`} />
            Risincronizza dai collegamenti esistenti
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!ricetteDisponibili && (
          <p className="text-sm text-amber-700">
            Non riesco a leggere le ricette di Lotti in questo momento: puoi comunque vedere l'elenco,
            ma l'associazione non e' disponibile finche' il collegamento non torna attivo.
          </p>
        )}
        {dati.prodotti.map((p) => (
          <RigaProdotto
            key={p.id}
            prodotto={p}
            ricette={ricette}
            ricetteDisponibili={ricetteDisponibili}
            valoreRicerca={ricercaPerProdotto[p.id] || ''}
            onCambiaRicerca={(v) => setRicercaPerProdotto((s) => ({ ...s, [p.id]: v }))}
            onAssocia={associa}
          />
        ))}
      </CardContent>
    </Card>
  );
};

const RigaProdotto = ({ prodotto, ricette, ricetteDisponibili, valoreRicerca, onCambiaRicerca, onAssocia }) => {
  const [aperto, setAperto] = useState(false);
  const filtrate = useMemo(() => {
    const q = valoreRicerca.trim().toLowerCase();
    if (!q) return ricette.slice(0, 8);
    return ricette.filter((r) => r.nome.toLowerCase().includes(q)).slice(0, 8);
  }, [valoreRicerca, ricette]);

  return (
    <div className="bg-white rounded-lg border border-amber-200 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-medium">{prodotto.name_it}</div>
          {prodotto.description_it && (
            <div className="text-xs text-gray-500 line-clamp-1">{prodotto.description_it}</div>
          )}
          {prodotto.lotti_ref && (
            <div className="text-xs text-gray-500">Collegato a ricetta Lotti: {prodotto.lotti_ref}</div>
          )}
        </div>
        {ricetteDisponibili && (
          <Button size="sm" variant="secondary" onClick={() => setAperto((a) => !a)}>
            <Link2 className="w-4 h-4 mr-1" /> Collega a una ricetta
          </Button>
        )}
      </div>
      {aperto && (
        <div className="mt-3 space-y-2">
          <Input
            placeholder="Cerca la ricetta di Lotti per nome..."
            value={valoreRicerca}
            onChange={(e) => onCambiaRicerca(e.target.value)}
          />
          <div className="max-h-48 overflow-y-auto divide-y">
            {filtrate.length === 0 && (
              <p className="text-sm text-gray-500 py-2">Nessuna ricetta trovata con questo nome.</p>
            )}
            {filtrate.map((r) => (
              <button
                key={r.doc_id}
                className="w-full text-left py-2 px-1 hover:bg-amber-50 flex items-center justify-between"
                onClick={() => { onAssocia(prodotto.id, r.doc_id, r.nome); setAperto(false); }}
              >
                <span>{r.nome}</span>
                <span className="text-xs text-gray-500">
                  {r.allergeni.length > 0 ? nomeAllergeni(r.allergeni) : 'nessun allergene nella ricetta'}
                  {!r.verificato && ' · da verificare'}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default AllergeniMancanti;

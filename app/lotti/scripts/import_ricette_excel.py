"""
Script import ricette da Excel — sovrascrive ingredienti nelle ricette esistenti,
crea nuove ricette per quelle non presenti.
"""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
import uuid
from datetime import datetime, timezone

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

RECIPES_DATA = {
    "arancini riso": ["sale", "sedano", "carote", "olio extravergine oliva"],
    "crocche patate": ["sale", "olio extravergine oliva"],
    "frittatina bucatini": ["sale", "latte", "margarina sfoglia", "farina 0", "carote", "piselli", "olio extravergine oliva", "basilico/rosmarino/prezzemolo"],
    "friarielli in padella": ["friarielli", "sale", "olio extravergine oliva"],
    "peperoni in padella": ["peperoni", "sale", "olio extravergine oliva"],
    "melanzane in padella": ["melanzane", "sale", "olio extravergine oliva"],
    "polpettine di carne": ["macinato", "olio extravergine oliva", "sale"],
    "zucchine alla scapece": ["zucchine", "sale", "olio extravergine oliva"],
    "zucchine in padella": ["zucchine", "sale", "olio extravergine oliva"],
    "scarole ripassate": ["scarola", "sale", "olio extravergine oliva", "basilico/rosmarino/prezzemolo"],
    "crostone di ricotta": ["farina 0", "sale", "ricotta omogeneizzata"],
    "pizza parigina": ["farina 0", "sale", "lievito", "strutto", "pomodori", "sottilette", "margarina sfoglia"],
    "pizza margherita": ["farina 0", "sale", "lievito", "strutto", "pelati", "fiori e provola"],
    "pizza farcita friarielli": ["farina 0", "sale", "lievito", "strutto", "passata di pomodoro", "fiori e provola", "friarielli"],
    "focaccia bianca": ["farina 0", "sale", "lievito", "strutto"],
    "focaccia margherita": ["farina 0", "sale", "lievito", "strutto", "pomodori", "fiori e provola"],
    "ragù di pomodoro": ["pelati", "olio extravergine oliva", "sale"],
    "salpicon di carne": ["tritato misto bovino/suino", "olio extravergine oliva", "salame", "piselli", "basilico/rosmarino/prezzemolo"],
    "prosciutto cotto": ["prosciutto cotto"],
    "prosciutto crudo": ["prosciutto crudo"],
    "porchetta di ariccia": ["porchetta"],
    "salame napoletano": ["salame napoli"],
    "salsa cruda di pomodoro": ["pomodori", "sale", "olio extravergine oliva"],
    "melanzane fritta involtino": ["involtino melanzane", "sale", "olio extravergine oliva"],
    "melanzana al forno": ["melanzane", "sale", "olio extravergine oliva"],
    "zucca al forno": ["zucchine", "olio extravergine oliva", "sale", "basilico/rosmarino/prezzemolo"],
    "funghi trifolati": ["sale", "olio extravergine oliva", "basilico/rosmarino/prezzemolo"],
    "wrustel di suino": ["wrustel"],
    "crema pasticciera": ["amido", "zucchero semolato", "tuorlo d'uovo pastorizzato", "latte"],
    "babà": ["farina 0", "sale", "margarina crema", "tuorlo d'uovo pastorizzato", "lievito"],
    "babà misù": ["farina 0", "sale", "margarina crema", "tuorlo d'uovo pastorizzato", "lievito", "mascarpone", "latte", "amido", "cioccolato", "panna"],
    "biscotto di pasta frolla al cioccolato": ["farina 0", "strutto", "sale", "zucchero semolato", "cacao amaro"],
    "brioche": ["farina 0", "margarina crema", "lievito", "tuorlo d'uovo pastorizzato", "aroma croissant", "latte", "sale"],
    "brioche mignon": ["farina 0", "margarina crema", "lievito", "tuorlo d'uovo pastorizzato", "aroma croissant", "latte", "sale"],
    "cannolo siciliano": ["cannoli max scuri x 100pz", "ricotta omogeneizzata"],
    "caprese cioccolato": ["cioccolato", "nuppy nocciola", "surrogato fondente", "zucchero semolato", "margarina sfoglia", "mix cake nature", "pasta di mandorle"],
    "caprese limone": ["nuppy nocciola", "cioccolato", "zucchero semolato", "pasta di mandorle", "margarina sfoglia", "mix cake nature", "limoni"],
    "cassatina": ["farina 0", "zucchero semolato", "lievito", "mix cake nature", "tuorlo d'uovo pastorizzato", "ricotta tipo roma", "naspro", "passata visciola", "cioccolato"],
    "cervellatine": ["salame", "sale", "olio extravergine oliva"],
    "cheesecake": ["farina 0", "strutto", "sale", "zucchero semolato", "tuorlo d'uovo pastorizzato", "panna"],
    "coda di aragosta": ["coda d'aragosta"],
    "cornetto alla crema": ["farina 0", "margarina crema", "lievito", "tuorlo d'uovo pastorizzato", "aroma croissant", "latte", "sale"],
    "cornetto alla crema amarena": ["farina 0", "margarina crema", "lievito", "uova", "aroma croissant", "latte", "sale", "amido", "amarena naturale intera in sciroppo"],
    "cornetto brioche": ["farina 0", "margarina crema", "lievito", "uova", "aroma croissant", "latte", "sale"],
    "cornetto ischitano": ["farina 0", "margarina crema", "lievito", "uova", "aroma croissant", "latte", "sale", "margarina sfoglia", "amido", "amarena intera tantofrutto"],
    "cornetto mignon": ["farina 0", "margarina sfoglia", "lievito", "tuorlo d'uovo pastorizzato", "aroma croissant", "latte", "sale"],
    "cornetto sfoglia": ["farina 0", "margarina sfoglia", "lievito", "uova", "aroma croissant", "latte", "sale"],
    "crema chantilly": ["amido", "latte", "zucchero semolato", "tuorlo d'uovo pastorizzato", "panna"],
    "crostatina albicocca": ["farina 0", "strutto", "passata albicocca", "zucchero semolato"],
    "crostatina cioccolato": ["farina 0", "strutto", "zucchero semolato", "sale", "nocciola"],
    "delizia al limone": ["farina 0", "sale", "amido", "limoni", "tuorlo d'uovo pastorizzato", "zucchero semolato", "panna"],
    "fagioli uccelletto": ["fagioli borlotti", "sale", "olio extravergine oliva", "salame napoli", "pomodori ciliegine"],
    "fiocco di neve": ["farina 0", "margarina sfoglia", "lievito", "uova", "aroma croissant", "latte", "sale", "panna", "ricotta omogeneizzata"],
    "francesina cioccolato": ["farina 0", "margarina sfoglia", "zucchero semolato", "amido", "latte", "cioccolato", "tuorlo d'uovo pastorizzato", "nocciola"],
    "francesina crema": ["farina 0", "margarina sfoglia", "zucchero semolato", "amido", "latte", "tuorlo d'uovo pastorizzato"],
    "krans cioccolato": ["farina 0", "margarina crema", "lievito", "uova", "aroma croissant", "latte", "sale", "gocce cioccolato fondente"],
    "krans uvetta": ["farina 0", "margarina crema", "lievito", "uova", "aroma croissant", "latte", "sale", "uva sultanina"],
    "pan di spagna": ["farina 0", "sale", "zucchero semolato", "tuorlo d'uovo pastorizzato", "margarina crema"],
    "panna": ["panna", "sale"],
    "pasta choux": ["farina 0", "uova", "sale", "margarina crema"],
    "pasta di mandorle": ["pasta di mandorle"],
    "pasta frolla basi abbattute": ["farina 0", "strutto", "zucchero semolato", "sale"],
    "pasta frolla fresca": ["farina 0", "strutto", "zucchero semolato", "sale"],
    "peperoni": ["peperoni"],
    "pasta sfoglia": ["farina 0", "sale", "margarina crema"],
    "pasticcino crema": ["farina 0", "strutto", "zucchero semolato", "sale", "latte", "amido", "tuorlo d'uovo pastorizzato"],
    "pasticcino limone": ["farina 0", "strutto", "zucchero semolato", "sale", "limoni"],
    "pasticcino pistacchio": ["farina 0", "strutto", "zucchero semolato", "sale", "nuppy pistacchio"],
    "pastiera": ["farina 0", "strutto", "zucchero a velo", "sale", "grano", "latte", "uova"],
    "prussiana": ["farina 00 caputo", "sale", "zucchero semolato", "margarina crema"],
    "ricotta zuccherata": ["ricotta zuccherata congelata"],
    "rustico": ["farina 0", "ricotta tipo roma", "sale", "wrustel", "salame", "strutto", "zucchero semolato"],
    "salsiccia di tacchino": ["basilico/rosmarino/prezzemolo", "salsiccia puro suino", "olio extravergine oliva", "sale"],
    "salumi misti": ["porchetta", "wrustel", "salame", "grana padano"],
    "sfogliatella frolla": ["farina 0", "sale", "zucchero semolato", "uova", "semola", "gelatina neutra", "strutto"],
    "sfogliatella riccia": ["tappi per ricce grandi", "sale", "zucchero semolato", "uova", "semola", "canditi", "strutto"],
    "strudel al cioccolato": ["farina 0", "sale", "margarina crema", "mele", "latte", "zucchero semolato", "amido", "uova", "cioccolato"],
    "strudel di mele": ["farina 0", "sale", "margarina crema", "mele", "latte", "zucchero semolato", "amido", "uova", "aromi"],
    "tiramisù": ["farina 0", "sale", "zucchero semolato", "uova", "mascarpone", "panna", "cioccolato"],
    "treccia": ["farina 0", "sale", "zucchero semolato", "lievito", "aroma croissant", "latte", "uova", "margarina crema"],
    "vesuvio": ["tappi per ricce grandi", "strutto"],
}

async def import_recipes():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    created = 0
    updated = 0
    skipped = 0
    
    for nome_ricetta, ingredienti_nomi in RECIPES_DATA.items():
        # Cerca ricetta esistente (case-insensitive)
        existing = await db.ricette.find_one(
            {"nome": {"$regex": f"^{nome_ricetta}$", "$options": "i"}},
            {"_id": 0}
        )
        
        # Costruisci ingredienti_dettaglio
        ingredienti_dettaglio = []
        for ing_nome in ingredienti_nomi:
            ingredienti_dettaglio.append({
                "nome": ing_nome,
                "quantita": "q.b.",
                "unita_misura": "g",
                "prodotto_dizionario_id": None,
                "prezzo_kg": None,
                "costo_calcolato": None,
            })
        
        if existing:
            # Aggiorna ingredienti solo se la ricetta esistente ha meno ingredienti o ingredienti diversi
            existing_ings = set(i.get("nome","").lower() for i in (existing.get("ingredienti_dettaglio") or []))
            new_ings = set(i.lower() for i in ingredienti_nomi)
            
            if not existing_ings or (new_ings - existing_ings):
                # Merge: mantieni ingredienti esistenti con quantità, aggiungi nuovi
                merged = list(existing.get("ingredienti_dettaglio") or [])
                existing_names_lower = set(i.get("nome","").lower() for i in merged)
                
                for ing in ingredienti_dettaglio:
                    if ing["nome"].lower() not in existing_names_lower:
                        merged.append(ing)
                
                await db.ricette.update_one(
                    {"id": existing["id"]},
                    {"$set": {
                        "ingredienti_dettaglio": merged,
                        "ingredienti": [i["nome"] for i in merged],
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
                updated += 1
                print(f"  ↻ {nome_ricetta}: aggiornata ({len(merged)} ingredienti)")
            else:
                skipped += 1
        else:
            # Crea nuova ricetta
            reparto = "rosticceria"
            # Pasticceria keywords
            pasticceria_kw = ["babà", "brioche", "cornetto", "crema", "crostat", "delizia", "fiocco", 
                             "francesina", "krans", "pan di spagna", "pasta frolla", "pasticcino",
                             "pastiera", "prussiana", "sfogliatella", "strudel", "tiramisù", "treccia",
                             "caprese", "cassatina", "cannolo", "cheesecake", "coda", "biscotto",
                             "panna", "pasta choux", "pasta di mandorle", "ricotta zuccherata", "vesuvio",
                             "pasta sfoglia"]
            for kw in pasticceria_kw:
                if kw in nome_ricetta.lower():
                    reparto = "pasticceria"
                    break
            
            doc = {
                "id": str(uuid.uuid4()),
                "nome": nome_ricetta,
                "ingredienti": ingredienti_nomi,
                "ingredienti_dettaglio": ingredienti_dettaglio,
                "porzioni": 10,
                "note": "",
                "costo_totale": 0,
                "costo_porzione": 0,
                "completezza": f"0/{len(ingredienti_nomi)}",
                "reparto": reparto,
                "allergeni": [],
                "allergeni_auto": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.ricette.insert_one(doc)
            created += 1
            print(f"  + {nome_ricetta}: creata ({reparto}, {len(ingredienti_nomi)} ingredienti)")
    
    print(f"\n=== RISULTATO ===")
    print(f"Create: {created}")
    print(f"Aggiornate: {updated}")
    print(f"Invariate: {skipped}")
    print(f"Totale processate: {created + updated + skipped}")
    
    # Count totale ricette
    total = await db.ricette.count_documents({})
    print(f"Ricette totali nel DB: {total}")
    
    client.close()

asyncio.run(import_recipes())

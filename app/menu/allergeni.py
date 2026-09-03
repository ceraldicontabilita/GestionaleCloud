"""I 14 allergeni del Reg. UE 1169/2011, con gli stessi id usati dai prodotti
(``allergens: ["gluten", "milk", ...]``). Sono il valore iniziale della
collezione ``menu_allergens`` quando e' vuota (prima migrazione o installazione
nuova); dopo, la collezione e' l'unica fonte."""
ALLERGENI_DEFAULT = [
    {"id": "gluten", "name": "Gluten", "nameIT": "Glutine", "icon": "🌾", "descriptionIT": "Cereali contenenti glutine", "descriptionEN": "Cereals containing gluten"},
    {"id": "milk", "name": "Milk", "nameIT": "Latte", "icon": "🥛", "descriptionIT": "Latte e derivati", "descriptionEN": "Milk and derivatives"},
    {"id": "eggs", "name": "Eggs", "nameIT": "Uova", "icon": "🥚", "descriptionIT": "Uova e derivati", "descriptionEN": "Eggs and derivatives"},
    {"id": "nuts", "name": "Nuts", "nameIT": "Frutta a guscio", "icon": "🌰", "descriptionIT": "Frutta a guscio", "descriptionEN": "Nuts"},
    {"id": "fish", "name": "Fish", "nameIT": "Pesce", "icon": "🐟", "descriptionIT": "Pesce", "descriptionEN": "Fish"},
    {"id": "soy", "name": "Soy", "nameIT": "Soia", "icon": "🫘", "descriptionIT": "Soia", "descriptionEN": "Soy"},
    {"id": "sulphites", "name": "Sulphites", "nameIT": "Solfiti", "icon": "🍷", "descriptionIT": "Solfiti", "descriptionEN": "Sulphites"},
    {"id": "crustaceans", "name": "Crustaceans", "nameIT": "Crostacei", "icon": "🦐", "descriptionIT": "Crostacei", "descriptionEN": "Crustaceans"},
    {"id": "molluscs", "name": "Molluscs", "nameIT": "Molluschi", "icon": "🦪", "descriptionIT": "Molluschi", "descriptionEN": "Molluscs"},
    {"id": "celery", "name": "Celery", "nameIT": "Sedano", "icon": "🥬", "descriptionIT": "Sedano", "descriptionEN": "Celery"},
    {"id": "mustard", "name": "Mustard", "nameIT": "Senape", "icon": "🌭", "descriptionIT": "Senape", "descriptionEN": "Mustard"},
    {"id": "sesame", "name": "Sesame", "nameIT": "Sesamo", "icon": "🫚", "descriptionIT": "Sesamo", "descriptionEN": "Sesame"},
    {"id": "lupin", "name": "Lupin", "nameIT": "Lupini", "icon": "🫛", "descriptionIT": "Lupini", "descriptionEN": "Lupin"},
    {"id": "peanuts", "name": "Peanuts", "nameIT": "Arachidi", "icon": "🥜", "descriptionIT": "Arachidi", "descriptionEN": "Peanuts"},
]

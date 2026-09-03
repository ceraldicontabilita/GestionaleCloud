from fastapi import APIRouter
import os

from app.menu.supabase_client import supabase

router = APIRouter()

MENU_CATEGORIES = [
    {
        "id": 1,
        "name": "Bar & Desserts",
        "nameIT": "Bar e Dolci",
        "image": "https://img.qromo.io/businesses/1LjmB37KIM7oGD7-full.jpeg"
    },
    {
        "id": 2,
        "name": "Food",
        "nameIT": "Cibo",
        "image": "https://img.qromo.io/businesses/glj0JlFiYPmeSp3-full.jpeg"
    },
    {
        "id": 3,
        "name": "Cocktails, Beers & Spirits",
        "nameIT": "Cocktail, Birre e Liquori",
        "image": "https://img.qromo.io/businesses/xKqXA9ChObqmoy6-full.jpeg"
    }
]

SUBCATEGORIES = [
    # Bar & Desserts
    {"id": 11, "category_id": 1, "name": "Coffee Shop", "nameIT": "Caffetteria", "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/1_bar-1024x682.jpg"},
    {"id": 12, "category_id": 1, "name": "Pastry", "nameIT": "Pasticceria", "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/1_pasticceria-1024x682.jpg"},
    {"id": 13, "category_id": 1, "name": "Croissants", "nameIT": "Cornetti", "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/1_pasticceria-1024x682.jpg"},
    # Food
    {"id": 21, "category_id": 2, "name": "Fried Delicacies", "nameIT": "Frittatine", "image": "https://ceraldicaffe.it/wp-content/uploads/2019/03/1_gastronomia-1024x682.jpg"},
    {"id": 22, "category_id": 2, "name": "Gastronomy", "nameIT": "Gastronomia", "image": "https://ceraldicaffe.it/wp-content/uploads/2019/03/1_gastronomia-1024x682.jpg"},
    {"id": 23, "category_id": 2, "name": "English Breakfast", "nameIT": "Colazione Inglese", "image": "https://ceraldicaffe.it/wp-content/uploads/2019/03/1_food-1-1013x1024.jpg"},
    # Cocktails
    {"id": 31, "category_id": 3, "name": "Signature Cocktails", "nameIT": "Cocktail Signature", "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/1_aperitivi-1024x682.jpg"},
    {"id": 32, "category_id": 3, "name": "Classic Cocktails", "nameIT": "Cocktail Classici", "image": "https://img.qromo.io/businesses/xKqXA9ChObqmoy6-full.jpeg"},
    {"id": 33, "category_id": 3, "name": "Beers & Spirits", "nameIT": "Birre e Liquori", "image": "https://img.qromo.io/businesses/xKqXA9ChObqmoy6-full.jpeg"},
    {"id": 34, "category_id": 3, "name": "Soft Drinks", "nameIT": "Bibite", "image": "https://img.qromo.io/businesses/xKqXA9ChObqmoy6-full.jpeg"}
]

PRODUCTS = [
    # === Caffetteria (id: 11) ===
    {"id": 101, "category_id": 1, "subcategory_id": 11, "name": "Caffè Ceraldi", "nameIT": "Caffè Ceraldi", "price": "3.50€", "description": "Ecuadorian dark chocolate fondue, artisan coffee cream, fresh whipped cream", "descriptionIT": "Fondo di Cioccolata calda fondente equador, crema di caffè artigianale, panna fresca montata", "allergens": ["milk"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/2_bar-1024x682.jpg"},
    {"id": 102, "category_id": 1, "subcategory_id": 11, "name": "Caffè Viennese", "nameIT": "Caffè Viennese", "price": "3.50€", "description": "Espresso, cane sugar cream, Strega Alberti, fresh whipped cream", "descriptionIT": "Caffè espresso, crema di zucchero di canna, Strega Alberti, panna fresca montata", "allergens": ["milk"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/4_bar-1024x682.jpg"},
    {"id": 103, "category_id": 1, "subcategory_id": 11, "name": "Caffè CaldoFreddo", "nameIT": "Caffè CaldoFreddo", "price": "2.50€", "description": "Espresso with cold frothed milk", "descriptionIT": "Caffè espresso, latte montato a freddo", "allergens": ["milk"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/3_bar-1024x682.jpg"},
    {"id": 104, "category_id": 1, "subcategory_id": 11, "name": "Caffè Michelino", "nameIT": "Caffè Michelino", "price": "3.00€", "description": "Espresso, cane sugar cream, melted whipped cream, cocoa", "descriptionIT": "Caffè espresso, crema di zucchero di canna, panna sciolta, cacao", "allergens": ["milk"]},
    {"id": 105, "category_id": 1, "subcategory_id": 11, "name": "Cappuccino", "nameIT": "Cappuccino", "price": "1.50€", "allergens": ["milk"]},
    {"id": 106, "category_id": 1, "subcategory_id": 11, "name": "Cappuccino with Soy Milk", "nameIT": "Cappuccino Latte di Soia", "price": "2.00€", "allergens": ["soy"]},
    {"id": 107, "category_id": 1, "subcategory_id": 11, "name": "Cappuccino with Almond Milk", "nameIT": "Cappuccino Latte di Mandorla", "price": "2.00€", "allergens": ["nuts"]},
    {"id": 108, "category_id": 1, "subcategory_id": 11, "name": "Cappuccino with Oat Milk", "nameIT": "Cappuccino Latte d'Avena", "price": "2.00€", "allergens": ["gluten"]},
    {"id": 109, "category_id": 1, "subcategory_id": 11, "name": "Latte Macchiato", "nameIT": "Latte Macchiato", "price": "2.00€", "allergens": ["milk"]},
    {"id": 110, "category_id": 1, "subcategory_id": 11, "name": "Espresso", "nameIT": "Caffè Espresso", "price": "1.20€", "allergens": []},
    {"id": 111, "category_id": 1, "subcategory_id": 11, "name": "Double Espresso", "nameIT": "Caffè Doppio", "price": "2.00€", "allergens": []},
    {"id": 112, "category_id": 1, "subcategory_id": 11, "name": "Caffè Macchiato", "nameIT": "Caffè Macchiato", "price": "1.30€", "allergens": ["milk"]},
    {"id": 113, "category_id": 1, "subcategory_id": 11, "name": "Caffè Macchiato Freddo", "nameIT": "Caffè Macchiato Freddo", "price": "1.50€", "allergens": ["milk"]},
    {"id": 114, "category_id": 1, "subcategory_id": 11, "name": "Ristretto", "nameIT": "Ristretto", "price": "1.20€", "allergens": []},
    {"id": 115, "category_id": 1, "subcategory_id": 11, "name": "Lungo", "nameIT": "Caffè Lungo", "price": "1.30€", "allergens": []},
    {"id": 116, "category_id": 1, "subcategory_id": 11, "name": "Decaffeinated", "nameIT": "Caffè Decaffeinato", "price": "1.30€", "allergens": []},
    {"id": 117, "category_id": 1, "subcategory_id": 11, "name": "Americano", "nameIT": "Caffè Americano", "price": "2.00€", "allergens": []},
    {"id": 118, "category_id": 1, "subcategory_id": 11, "name": "Marocchino", "nameIT": "Marocchino", "price": "2.00€", "allergens": ["milk"]},
    {"id": 119, "category_id": 1, "subcategory_id": 11, "name": "Caffè Corretto", "nameIT": "Caffè Corretto", "price": "2.00€", "allergens": ["sulphites"]},
    {"id": 120, "category_id": 1, "subcategory_id": 11, "name": "Hot Chocolate", "nameIT": "Cioccolata Calda", "price": "4.00€", "allergens": ["milk"]},
    {"id": 121, "category_id": 1, "subcategory_id": 11, "name": "Hot Chocolate with Cream", "nameIT": "Cioccolata con Panna", "price": "4.50€", "allergens": ["milk"]},
    {"id": 122, "category_id": 1, "subcategory_id": 11, "name": "Tea", "nameIT": "Tè", "price": "2.00€", "allergens": []},
    {"id": 123, "category_id": 1, "subcategory_id": 11, "name": "Herbal Tea", "nameIT": "Tisana", "price": "2.50€", "allergens": []},
    {"id": 124, "category_id": 1, "subcategory_id": 11, "name": "Ginseng", "nameIT": "Ginseng", "price": "2.00€", "allergens": ["milk"]},
    {"id": 125, "category_id": 1, "subcategory_id": 11, "name": "Barley Coffee", "nameIT": "Orzo", "price": "1.50€", "allergens": []},
    {"id": 126, "category_id": 1, "subcategory_id": 11, "name": "Fresh Orange Juice", "nameIT": "Spremuta d'Arancia", "price": "4.00€", "allergens": []},
    {"id": 127, "category_id": 1, "subcategory_id": 11, "name": "Grapefruit Juice", "nameIT": "Spremuta di Pompelmo", "price": "4.50€", "allergens": []},
    {"id": 128, "category_id": 1, "subcategory_id": 11, "name": "Mixed Fruit Juice", "nameIT": "Estratto Frutta Mista", "price": "5.00€", "allergens": []},
    {"id": 129, "category_id": 1, "subcategory_id": 11, "name": "Green Juice", "nameIT": "Estratto Verde", "price": "5.00€", "allergens": []},
    {"id": 130, "category_id": 1, "subcategory_id": 11, "name": "Carrot Juice", "nameIT": "Centrifugato Carota", "price": "4.50€", "allergens": []},
    {"id": 131, "category_id": 1, "subcategory_id": 11, "name": "Iced Coffee", "nameIT": "Caffè Freddo", "price": "2.50€", "allergens": []},
    {"id": 132, "category_id": 1, "subcategory_id": 11, "name": "Iced Cappuccino", "nameIT": "Cappuccino Freddo", "price": "3.00€", "allergens": ["milk"]},
    {"id": 133, "category_id": 1, "subcategory_id": 11, "name": "Frappe", "nameIT": "Frappè", "price": "4.00€", "allergens": ["milk"]},
    {"id": 134, "category_id": 1, "subcategory_id": 11, "name": "Smoothie", "nameIT": "Smoothie", "price": "5.00€", "allergens": []},
    {"id": 135, "category_id": 1, "subcategory_id": 11, "name": "Iced Tea", "nameIT": "Tè Freddo", "price": "3.00€", "allergens": []},
    
    # === Pasticceria (id: 12) ===
    {"id": 201, "category_id": 1, "subcategory_id": 12, "name": "Sfogliatella Riccia", "nameIT": "Sfogliatella Riccia", "price": "2.00€", "allergens": ["gluten", "milk", "eggs"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/10_pasticceria-1024x682.jpg"},
    {"id": 202, "category_id": 1, "subcategory_id": 12, "name": "Sfogliatella Frolla", "nameIT": "Sfogliatella Frolla", "price": "2.00€", "allergens": ["gluten", "milk", "eggs"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/9_pasticceria-1024x682.jpg"},
    {"id": 203, "category_id": 1, "subcategory_id": 12, "name": "Sfogliatella Santa Rosa", "nameIT": "Sfogliatella Santa Rosa", "price": "2.50€", "allergens": ["gluten", "milk", "eggs", "nuts"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/11_pasticceria-1024x682.jpg"},
    {"id": 204, "category_id": 1, "subcategory_id": 12, "name": "Babà", "nameIT": "Babà", "price": "2.50€", "allergens": ["gluten", "eggs", "sulphites"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/7_pasticceria-1024x682.jpg"},
    {"id": 205, "category_id": 1, "subcategory_id": 12, "name": "Babà Cream Amarena", "nameIT": "Babà Crema e Amarena", "price": "3.50€", "allergens": ["gluten", "eggs", "milk", "sulphites"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/4_pasticceria.jpg"},
    {"id": 206, "category_id": 1, "subcategory_id": 12, "name": "Babà Cream Strawberry", "nameIT": "Babà Panna e Fragola", "price": "3.50€", "allergens": ["gluten", "eggs", "milk", "sulphites"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/2_pasticceria-1024x682.jpg"},
    {"id": 207, "category_id": 1, "subcategory_id": 12, "name": "Strawberry Tart", "nameIT": "Crostatina Fragole", "price": "3.00€", "allergens": ["gluten", "eggs", "milk"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/1_pasticceria-1024x682.jpg"},
    {"id": 208, "category_id": 1, "subcategory_id": 12, "name": "Fruit Tart", "nameIT": "Crostatina Frutta", "price": "3.00€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 209, "category_id": 1, "subcategory_id": 12, "name": "Tiramisù", "nameIT": "Tiramisù", "price": "4.00€", "allergens": ["eggs", "milk", "gluten"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/5_pasticceria.jpg"},
    {"id": 210, "category_id": 1, "subcategory_id": 12, "name": "Berry Cheesecake", "nameIT": "Cheesecake Frutti di Bosco", "price": "4.50€", "allergens": ["milk", "gluten", "eggs"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/6_pasticceria-1024x681.jpg"},
    {"id": 211, "category_id": 1, "subcategory_id": 12, "name": "Pan di Stelle Semifreddo", "nameIT": "Semifreddo Pan di Stelle", "price": "4.00€", "allergens": ["milk", "gluten", "eggs", "nuts"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/3_pasticceria-1024x682.jpg"},
    {"id": 212, "category_id": 1, "subcategory_id": 12, "name": "Zeppola San Giuseppe", "nameIT": "Zeppola di San Giuseppe", "price": "2.50€", "allergens": ["gluten", "eggs", "milk"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/8_pasticceria-1024x682.jpg"},
    {"id": 213, "category_id": 1, "subcategory_id": 12, "name": "Pastiera Napoletana", "nameIT": "Pastiera Napoletana", "price": "12.50€", "allergens": ["gluten", "eggs", "milk", "nuts"]},
    {"id": 214, "category_id": 1, "subcategory_id": 12, "name": "Cannoli Siciliani", "nameIT": "Cannoli Siciliani", "price": "3.00€", "allergens": ["gluten", "milk", "eggs"]},
    {"id": 215, "category_id": 1, "subcategory_id": 12, "name": "Biscotti Assortiti", "nameIT": "Biscotti Assortiti", "price": "2.00€", "allergens": ["gluten", "eggs", "milk"]},
    
    # === Cornetti (id: 13) ===
    {"id": 301, "category_id": 1, "subcategory_id": 13, "name": "Croissant Plain", "nameIT": "Cornetto Vuoto", "price": "1.70€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 302, "category_id": 1, "subcategory_id": 13, "name": "Croissant Cream", "nameIT": "Cornetto Crema", "price": "1.90€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 303, "category_id": 1, "subcategory_id": 13, "name": "Croissant Nutella", "nameIT": "Cornetto Nutella", "price": "1.90€", "allergens": ["gluten", "eggs", "milk", "nuts"]},
    {"id": 304, "category_id": 1, "subcategory_id": 13, "name": "Croissant Cream Amarena", "nameIT": "Cornetto Crema Amarena", "price": "1.90€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 305, "category_id": 1, "subcategory_id": 13, "name": "Croissant Jam", "nameIT": "Cornetto Marmellata", "price": "1.90€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 306, "category_id": 1, "subcategory_id": 13, "name": "Croissant Pistachio", "nameIT": "Cornetto Pistacchio", "price": "2.20€", "allergens": ["gluten", "eggs", "milk", "nuts"]},
    {"id": 307, "category_id": 1, "subcategory_id": 13, "name": "Vegan Croissant Plain", "nameIT": "Cornetto Vegano Vuoto", "price": "1.80€", "allergens": ["gluten"]},
    {"id": 308, "category_id": 1, "subcategory_id": 13, "name": "Vegan Croissant Honey", "nameIT": "Cornetto Vegano Miele", "price": "1.80€", "allergens": ["gluten"]},
    {"id": 309, "category_id": 1, "subcategory_id": 13, "name": "Vegan Croissant Jam", "nameIT": "Cornetto Vegano Marmellata", "price": "2.00€", "allergens": ["gluten"]},
    {"id": 310, "category_id": 1, "subcategory_id": 13, "name": "5 Grain Croissant Plain", "nameIT": "Cornetto 5 Cereali Vuoto", "price": "1.90€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 311, "category_id": 1, "subcategory_id": 13, "name": "5 Grain Croissant Berries", "nameIT": "Cornetto 5 Cereali Frutti Bosco", "price": "2.10€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 312, "category_id": 1, "subcategory_id": 13, "name": "5 Grain Croissant Pomegranate", "nameIT": "Cornetto 5 Cereali Melograno", "price": "2.10€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 313, "category_id": 1, "subcategory_id": 13, "name": "Wholemeal Croissant", "nameIT": "Cornetto Integrale", "price": "1.90€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 314, "category_id": 1, "subcategory_id": 13, "name": "Croissant Apricot", "nameIT": "Cornetto Albicocca", "price": "1.90€", "allergens": ["gluten", "eggs", "milk"]},
    
    # === Frittatine (id: 21) ===
    {"id": 401, "category_id": 2, "subcategory_id": 21, "name": "Frittatina Provola Peppers", "nameIT": "Frittatina Provola e Peperoni", "price": "2.00€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 402, "category_id": 2, "subcategory_id": 21, "name": "Frittatina Nerano", "nameIT": "Frittatina alla Nerano", "price": "2.00€", "description": "With zucchini and provolone", "descriptionIT": "Con zucchine e provolone", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 403, "category_id": 2, "subcategory_id": 21, "name": "Frittatina Porcini", "nameIT": "Frittatina Porcini e Provolone", "price": "2.00€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 404, "category_id": 2, "subcategory_id": 21, "name": "Frittatina Genovese", "nameIT": "Frittatina alla Genovese", "price": "2.00€", "description": "With stewed onions", "descriptionIT": "Con cipolle stufate", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 405, "category_id": 2, "subcategory_id": 21, "name": "Frittatina Sausage Friarielli", "nameIT": "Frittatina Salsiccia e Friarielli", "price": "2.00€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 406, "category_id": 2, "subcategory_id": 21, "name": "Frittatina Margherita", "nameIT": "Frittatina Margherita", "price": "1.80€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 407, "category_id": 2, "subcategory_id": 21, "name": "Frittatina Ham", "nameIT": "Frittatina Prosciutto", "price": "2.00€", "allergens": ["gluten", "eggs", "milk"]},
    
    # === Gastronomia (id: 22) ===
    {"id": 501, "category_id": 2, "subcategory_id": 22, "name": "Mini Pizza Margherita", "nameIT": "Mini Pizza Margherita", "price": "2.50€", "allergens": ["gluten", "milk", "sulphites"]},
    {"id": 502, "category_id": 2, "subcategory_id": 22, "name": "Mini Pizza Ham", "nameIT": "Mini Pizza Prosciutto", "price": "3.00€", "allergens": ["gluten", "milk", "sulphites"]},
    {"id": 503, "category_id": 2, "subcategory_id": 22, "name": "Mini Pizza Napoli", "nameIT": "Mini Pizza Napoli", "price": "3.00€", "description": "With anchovies and capers", "descriptionIT": "Con acciughe e capperi", "allergens": ["gluten", "milk", "fish", "sulphites"]},
    {"id": 504, "category_id": 2, "subcategory_id": 22, "name": "Panino Caprese", "nameIT": "Panino Caprese", "price": "4.00€", "allergens": ["gluten", "milk"]},
    {"id": 505, "category_id": 2, "subcategory_id": 22, "name": "Panino Ham Cheese", "nameIT": "Panino Prosciutto Formaggio", "price": "4.00€", "allergens": ["gluten", "milk"]},
    {"id": 506, "category_id": 2, "subcategory_id": 22, "name": "Panino Mortadella", "nameIT": "Panino Mortadella", "price": "3.50€", "allergens": ["gluten"]},
    {"id": 507, "category_id": 2, "subcategory_id": 22, "name": "Toast", "nameIT": "Toast", "price": "3.00€", "allergens": ["gluten", "milk"]},
    {"id": 508, "category_id": 2, "subcategory_id": 22, "name": "Tramezzino", "nameIT": "Tramezzino", "price": "2.50€", "allergens": ["gluten", "eggs"]},
    {"id": 509, "category_id": 2, "subcategory_id": 22, "name": "Octopus Potatoes", "nameIT": "Polipo e Patate Arrosto", "price": "8.00€", "allergens": ["molluscs"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/03/1_gastronomia-1024x682.jpg"},
    {"id": 510, "category_id": 2, "subcategory_id": 22, "name": "Grouper Millefeuille", "nameIT": "Millefoglie di Cernia", "price": "10.00€", "allergens": ["fish", "milk"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/03/2_gastronomia-1024x682.jpg"},
    {"id": 511, "category_id": 2, "subcategory_id": 22, "name": "Parmigiana Melanzane", "nameIT": "Parmigiana di Melanzane", "price": "7.00€", "allergens": ["milk", "eggs", "gluten", "sulphites"]},
    {"id": 512, "category_id": 2, "subcategory_id": 22, "name": "Mixed Salad", "nameIT": "Insalata Mista", "price": "5.00€", "allergens": []},
    
    # === Colazione Inglese (id: 23) ===
    {"id": 601, "category_id": 2, "subcategory_id": 23, "name": "Full English Breakfast", "nameIT": "Full English Breakfast", "price": "12.00€", "description": "Eggs, bacon, sausages, beans, mushrooms, tomatoes, toast and tea", "descriptionIT": "Uova, bacon, salsicce, fagioli, funghi, pomodori, pane tostato e tè", "allergens": ["gluten", "eggs", "milk"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/03/1_food-1-1013x1024.jpg"},
    {"id": 602, "category_id": 2, "subcategory_id": 23, "name": "Eggs Benedict", "nameIT": "Uova alla Benedict", "price": "8.00€", "allergens": ["gluten", "eggs", "milk"]},
    {"id": 603, "category_id": 2, "subcategory_id": 23, "name": "Scrambled Eggs Toast", "nameIT": "Uova Strapazzate Toast", "price": "6.00€", "allergens": ["gluten", "eggs", "milk"]},
    
    # === Cocktail Signature (id: 31) ===
    {"id": 701, "category_id": 3, "subcategory_id": 31, "name": "Aspritz", "nameIT": "Aspritz", "price": "6.00€", "description": "Homemade bitter with Amalfi citrus, Asprino wine", "descriptionIT": "Bitter artigianale con agrumi costiera, Asprino", "allergens": ["sulphites"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/1_aperitivi-1024x682.jpg"},
    {"id": 702, "category_id": 3, "subcategory_id": 31, "name": "Royal Maid Cuba", "nameIT": "Royal Maid in Cuba", "price": "7.00€", "description": "Gin, lime, peach liqueur, ginger, berry jam", "descriptionIT": "Gin, lime, liquore pesca, zenzero, marmellata", "allergens": [], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/2_aperitivi-1024x682.jpg"},
    {"id": 703, "category_id": 3, "subcategory_id": 31, "name": "Summerwind", "nameIT": "Summerwind", "price": "7.00€", "description": "Bacardi rum, lime, mint, cucumber, sparkling wine", "descriptionIT": "Rum Bacardi, lime, menta, cetriolo, spumante", "allergens": ["sulphites"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/3_aperitivi-1024x682.jpg"},
    {"id": 704, "category_id": 3, "subcategory_id": 31, "name": "Smoky Negroni", "nameIT": "Smoky Negroni", "price": "8.00€", "description": "Tanqueray gin, Cocchi vermouth, Campari, Laphroaig", "descriptionIT": "Tanqueray gin, vermouth Cocchi, Campari, Laphroaig", "allergens": ["sulphites"], "image": "https://ceraldicaffe.it/wp-content/uploads/2019/02/4_aperitivi-1024x682.jpg"},
    
    # === Cocktail Classici (id: 32) ===
    {"id": 801, "category_id": 3, "subcategory_id": 32, "name": "Aperol Spritz", "nameIT": "Aperol Spritz", "price": "6.00€", "allergens": ["sulphites"]},
    {"id": 802, "category_id": 3, "subcategory_id": 32, "name": "Mojito", "nameIT": "Mojito", "price": "7.00€", "allergens": []},
    {"id": 803, "category_id": 3, "subcategory_id": 32, "name": "Negroni", "nameIT": "Negroni", "price": "7.00€", "allergens": ["sulphites"]},
    {"id": 804, "category_id": 3, "subcategory_id": 32, "name": "Moscow Mule", "nameIT": "Moscow Mule", "price": "7.00€", "allergens": []},
    {"id": 805, "category_id": 3, "subcategory_id": 32, "name": "Gin Tonic", "nameIT": "Gin Tonic", "price": "7.00€", "allergens": ["sulphites"]},
    {"id": 806, "category_id": 3, "subcategory_id": 32, "name": "Daiquiri", "nameIT": "Daiquiri", "price": "7.00€", "allergens": []},
    {"id": 807, "category_id": 3, "subcategory_id": 32, "name": "Margarita", "nameIT": "Margarita", "price": "7.00€", "allergens": []},
    {"id": 808, "category_id": 3, "subcategory_id": 32, "name": "Caipirinha", "nameIT": "Caipirinha", "price": "6.50€", "allergens": []},
    
    # === Birre e Liquori (id: 33) ===
    {"id": 901, "category_id": 3, "subcategory_id": 33, "name": "Peroni", "nameIT": "Birra Peroni", "price": "4.00€", "allergens": ["gluten"]},
    {"id": 902, "category_id": 3, "subcategory_id": 33, "name": "Nastro Azzurro", "nameIT": "Nastro Azzurro", "price": "4.50€", "allergens": ["gluten"]},
    {"id": 903, "category_id": 3, "subcategory_id": 33, "name": "Craft Beer", "nameIT": "Birra Artigianale", "price": "5.00€", "allergens": ["gluten"]},
    {"id": 904, "category_id": 3, "subcategory_id": 33, "name": "Heineken", "nameIT": "Heineken", "price": "4.50€", "allergens": ["gluten"]},
    {"id": 905, "category_id": 3, "subcategory_id": 33, "name": "Limoncello", "nameIT": "Limoncello", "price": "3.50€", "allergens": ["sulphites"]},
    {"id": 906, "category_id": 3, "subcategory_id": 33, "name": "Prosecco", "nameIT": "Prosecco", "price": "5.00€", "allergens": ["sulphites"]},
    {"id": 907, "category_id": 3, "subcategory_id": 33, "name": "White Wine", "nameIT": "Vino Bianco", "price": "4.00€", "allergens": ["sulphites"]},
    {"id": 908, "category_id": 3, "subcategory_id": 33, "name": "Red Wine", "nameIT": "Vino Rosso", "price": "4.00€", "allergens": ["sulphites"]},
    {"id": 909, "category_id": 3, "subcategory_id": 33, "name": "Amaro", "nameIT": "Amaro", "price": "3.50€", "allergens": []},
    {"id": 910, "category_id": 3, "subcategory_id": 33, "name": "Grappa", "nameIT": "Grappa", "price": "4.00€", "allergens": []},
    {"id": 911, "category_id": 3, "subcategory_id": 33, "name": "Whisky", "nameIT": "Whisky", "price": "6.00€", "allergens": ["gluten"]},
    {"id": 912, "category_id": 3, "subcategory_id": 33, "name": "Vodka", "nameIT": "Vodka", "price": "5.00€", "allergens": []},
    {"id": 913, "category_id": 3, "subcategory_id": 33, "name": "Rum", "nameIT": "Rum", "price": "5.00€", "allergens": []},
    {"id": 914, "category_id": 3, "subcategory_id": 33, "name": "Gin", "nameIT": "Gin", "price": "5.50€", "allergens": []},
    
    # === Bibite (id: 34) ===
    {"id": 1001, "category_id": 3, "subcategory_id": 34, "name": "Coca Cola", "nameIT": "Coca Cola", "price": "3.00€", "allergens": []},
    {"id": 1002, "category_id": 3, "subcategory_id": 34, "name": "Coca Cola Zero", "nameIT": "Coca Cola Zero", "price": "3.00€", "allergens": []},
    {"id": 1003, "category_id": 3, "subcategory_id": 34, "name": "Fanta", "nameIT": "Fanta", "price": "3.00€", "allergens": []},
    {"id": 1004, "category_id": 3, "subcategory_id": 34, "name": "Sprite", "nameIT": "Sprite", "price": "3.00€", "allergens": []},
    {"id": 1005, "category_id": 3, "subcategory_id": 34, "name": "Water", "nameIT": "Acqua Naturale", "price": "1.50€", "allergens": []},
    {"id": 1006, "category_id": 3, "subcategory_id": 34, "name": "Sparkling Water", "nameIT": "Acqua Frizzante", "price": "1.50€", "allergens": []},
    {"id": 1007, "category_id": 3, "subcategory_id": 34, "name": "Fruit Juice", "nameIT": "Succo di Frutta", "price": "3.00€", "allergens": []},
    {"id": 1008, "category_id": 3, "subcategory_id": 34, "name": "Chinotto", "nameIT": "Chinotto", "price": "3.00€", "allergens": []}
]

ALLERGENS = [
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
    {"id": "peanuts", "name": "Peanuts", "nameIT": "Arachidi", "icon": "🥜", "descriptionIT": "Arachidi", "descriptionEN": "Peanuts"}
]



def _to_db_category(c):
    return {"id": c["id"], "name": c["name"], "name_it": c["nameIT"], "image": c.get("image")}


def _to_db_subcategory(s):
    return {
        "id": s["id"], "category_id": s["category_id"],
        "name": s["name"], "name_it": s["nameIT"], "image": s.get("image"),
    }


def _to_db_product(p):
    return {
        "id": p["id"], "category_id": p["category_id"], "subcategory_id": p["subcategory_id"],
        "name": p["name"], "name_it": p["nameIT"], "price": p["price"],
        "description": p.get("description"), "description_it": p.get("descriptionIT"),
        "allergens": p.get("allergens") or [], "image": p.get("image"),
    }


def _to_db_allergen(a):
    return {
        "id": a["id"], "name": a["name"], "name_it": a["nameIT"], "icon": a.get("icon"),
        "description_it": a.get("descriptionIT"), "description_en": a.get("descriptionEN"),
    }


@router.post("/api/admin/seed-once")
async def seed_database():
    # Ordine di cancellazione che rispetta i vincoli di foreign key (prodotti prima, poi
    # sottocategorie, poi categorie); gt(-1) seleziona tutte le righe (id sempre >= 0/testo).
    supabase.table("menu_products").delete().neq("id", -1).execute()
    supabase.table("menu_subcategories").delete().neq("id", -1).execute()
    supabase.table("menu_categories").delete().neq("id", -1).execute()
    supabase.table("menu_allergens").delete().neq("id", "___none___").execute()

    if MENU_CATEGORIES:
        supabase.table("menu_categories").insert([_to_db_category(c) for c in MENU_CATEGORIES]).execute()
    if SUBCATEGORIES:
        supabase.table("menu_subcategories").insert([_to_db_subcategory(s) for s in SUBCATEGORIES]).execute()
    if PRODUCTS:
        supabase.table("menu_products").insert([_to_db_product(p) for p in PRODUCTS]).execute()
    if ALLERGENS:
        supabase.table("menu_allergens").insert([_to_db_allergen(a) for a in ALLERGENS]).execute()

    return {
        "ok": True,
        "categories": len(MENU_CATEGORIES),
        "subcategories": len(SUBCATEGORIES),
        "products": len(PRODUCTS),
        "allergens": len(ALLERGENS)
    }

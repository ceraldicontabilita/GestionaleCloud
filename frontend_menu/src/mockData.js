export const menuCategories = [
  {
    id: 1,
    name: 'Bar & Desserts',
    nameIT: 'Bar e Dolci',
    image: 'https://img.qromo.io/businesses/1LjmB37KIM7oGD7-full.jpeg',
    subcategories: [
      {
        id: 11,
        name: 'Coffee Shop',
        nameIT: 'Caffetteria',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_bar-1024x682.jpg',
        items: [
          { id: 101, name: 'Caffè Ceraldi', nameIT: 'Caffè Ceraldi', price: '3.50€', description: 'Ecuadorian dark chocolate fondue, artisan coffee cream, fresh whipped cream', descriptionIT: 'Fondo di Cioccolata calda fondente equador, crema di caffè artigianale, panna fresca montata', allergens: ['milk'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/2_bar-1024x682.jpg' },
          { id: 102, name: 'Caffè Viennese', nameIT: 'Caffè Viennese', price: '3.50€', description: 'Espresso, cane sugar cream, Strega Alberti, fresh whipped cream', descriptionIT: 'Caffè espresso, crema di zucchero di canna, Strega Alberti, panna fresca montata', allergens: ['milk'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/4_bar-1024x682.jpg' },
          { id: 103, name: 'Caffè CaldoFreddo', nameIT: 'Caffè CaldoFreddo', price: '2.50€', description: 'Espresso with cold frothed milk', descriptionIT: 'Caffè espresso, latte montato a freddo', allergens: ['milk'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/3_bar-1024x682.jpg' },
          { id: 104, name: 'Caffè Michelino', nameIT: 'Caffè Michelino', price: '3.00€', description: 'Espresso, cane sugar cream, melted whipped cream, cocoa', descriptionIT: 'Caffè espresso, crema di zucchero di canna, panna sciolta, cacao', allergens: ['milk'] },
          { id: 105, name: 'Cappuccino', nameIT: 'Cappuccino', price: '1.50€', allergens: ['milk'] },
          { id: 106, name: 'Cappuccino with Soy Milk', nameIT: 'Cappuccino Latte di Soia', price: '2.00€', allergens: ['soy'] },
          { id: 107, name: 'Cappuccino with Almond Milk', nameIT: 'Cappuccino Latte di Mandorla', price: '2.00€', allergens: ['nuts'] },
          { id: 108, name: 'Cappuccino with Oat Milk', nameIT: 'Cappuccino Latte d\'Avena', price: '2.00€', allergens: ['gluten'] },
          { id: 109, name: 'Latte Macchiato', nameIT: 'Latte Macchiato', price: '2.00€', allergens: ['milk'] },
          { id: 110, name: 'Espresso', nameIT: 'Caffè Espresso', price: '1.20€', allergens: [] },
          { id: 111, name: 'Double Espresso', nameIT: 'Caffè Doppio', price: '2.00€', allergens: [] },
          { id: 112, name: 'Caffè Macchiato', nameIT: 'Caffè Macchiato', price: '1.30€', allergens: ['milk'] },
          { id: 113, name: 'Caffè Macchiato Freddo', nameIT: 'Caffè Macchiato Freddo', price: '1.50€', allergens: ['milk'] },
          { id: 114, name: 'Ristretto', nameIT: 'Ristretto', price: '1.20€', allergens: [] },
          { id: 115, name: 'Lungo', nameIT: 'Caffè Lungo', price: '1.30€', allergens: [] },
          { id: 116, name: 'Decaffeinated', nameIT: 'Caffè Decaffeinato', price: '1.30€', allergens: [] },
          { id: 117, name: 'Americano', nameIT: 'Caffè Americano', price: '2.00€', allergens: [] },
          { id: 118, name: 'Marocchino', nameIT: 'Marocchino', price: '2.00€', allergens: ['milk'] },
          { id: 119, name: 'Caffè Corretto', nameIT: 'Caffè Corretto', price: '2.00€', allergens: ['sulphites'] },
          { id: 120, name: 'Hot Chocolate', nameIT: 'Cioccolata Calda', price: '4.00€', allergens: ['milk'] },
          { id: 121, name: 'Hot Chocolate with Cream', nameIT: 'Cioccolata con Panna', price: '4.50€', allergens: ['milk'] },
          { id: 122, name: 'Tea', nameIT: 'Tè', price: '2.00€', allergens: [] },
          { id: 123, name: 'Herbal Tea', nameIT: 'Tisana', price: '2.50€', allergens: [] },
          { id: 124, name: 'Ginseng', nameIT: 'Ginseng', price: '2.00€', allergens: ['milk'] },
          { id: 125, name: 'Barley Coffee', nameIT: 'Orzo', price: '1.50€', allergens: [] },
          { id: 126, name: 'Fresh Orange Juice', nameIT: 'Spremuta d\'Arancia', price: '4.00€', allergens: [] },
          { id: 127, name: 'Grapefruit Juice', nameIT: 'Spremuta di Pompelmo', price: '4.50€', allergens: [] },
          { id: 128, name: 'Mixed Fruit Juice', nameIT: 'Estratto Frutta Mista', price: '5.00€', allergens: [] },
          { id: 129, name: 'Green Juice', nameIT: 'Estratto Verde', price: '5.00€', allergens: [] },
          { id: 130, name: 'Carrot Juice', nameIT: 'Centrifugato Carota', price: '4.50€', allergens: [] },
          { id: 131, name: 'Iced Coffee', nameIT: 'Caffè Freddo', price: '2.50€', allergens: [] },
          { id: 132, name: 'Iced Cappuccino', nameIT: 'Cappuccino Freddo', price: '3.00€', allergens: ['milk'] },
          { id: 133, name: 'Frappe', nameIT: 'Frappè', price: '4.00€', allergens: ['milk'] },
          { id: 134, name: 'Smoothie', nameIT: 'Smoothie', price: '5.00€', allergens: [] },
          { id: 135, name: 'Iced Tea', nameIT: 'Tè Freddo', price: '3.00€', allergens: [] }
        ]
      },
      {
        id: 12,
        name: 'Pastry',
        nameIT: 'Pasticceria',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_pasticceria-1024x682.jpg',
        items: [
          { id: 201, name: 'Sfogliatella Riccia', nameIT: 'Sfogliatella Riccia', price: '2.00€', allergens: ['gluten', 'milk', 'eggs'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/10_pasticceria-1024x682.jpg' },
          { id: 202, name: 'Sfogliatella Frolla', nameIT: 'Sfogliatella Frolla', price: '2.00€', allergens: ['gluten', 'milk', 'eggs'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/9_pasticceria-1024x682.jpg' },
          { id: 203, name: 'Sfogliatella Santa Rosa', nameIT: 'Sfogliatella Santa Rosa', price: '2.50€', allergens: ['gluten', 'milk', 'eggs', 'nuts'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/11_pasticceria-1024x682.jpg' },
          { id: 204, name: 'Babà', nameIT: 'Babà', price: '2.50€', allergens: ['gluten', 'eggs', 'sulphites'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/7_pasticceria-1024x682.jpg' },
          { id: 205, name: 'Babà Cream Amarena', nameIT: 'Babà Crema e Amarena', price: '3.50€', allergens: ['gluten', 'eggs', 'milk', 'sulphites'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/4_pasticceria.jpg' },
          { id: 206, name: 'Babà Cream Strawberry', nameIT: 'Babà Panna e Fragola', price: '3.50€', allergens: ['gluten', 'eggs', 'milk', 'sulphites'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/2_pasticceria-1024x682.jpg' },
          { id: 207, name: 'Strawberry Tart', nameIT: 'Crostatina Fragole', price: '3.00€', allergens: ['gluten', 'eggs', 'milk'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_pasticceria-1024x682.jpg' },
          { id: 208, name: 'Fruit Tart', nameIT: 'Crostatina Frutta', price: '3.00€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 209, name: 'Tiramisù', nameIT: 'Tiramisù', price: '4.00€', allergens: ['eggs', 'milk', 'gluten'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/5_pasticceria.jpg' },
          { id: 210, name: 'Berry Cheesecake', nameIT: 'Cheesecake Frutti di Bosco', price: '4.50€', allergens: ['milk', 'gluten', 'eggs'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/6_pasticceria-1024x681.jpg' },
          { id: 211, name: 'Pan di Stelle Semifreddo', nameIT: 'Semifreddo Pan di Stelle', price: '4.00€', allergens: ['milk', 'gluten', 'eggs', 'nuts'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/3_pasticceria-1024x682.jpg' },
          { id: 212, name: 'Zeppola San Giuseppe', nameIT: 'Zeppola di San Giuseppe', price: '2.50€', allergens: ['gluten', 'eggs', 'milk'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/8_pasticceria-1024x682.jpg' },
          { id: 213, name: 'Pastiera Napoletana', nameIT: 'Pastiera Napoletana', price: '12.50€', allergens: ['gluten', 'eggs', 'milk', 'nuts'] },
          { id: 214, name: 'Cannoli Siciliani', nameIT: 'Cannoli Siciliani', price: '3.00€', allergens: ['gluten', 'milk', 'eggs'] },
          { id: 215, name: 'Biscotti Assortiti', nameIT: 'Biscotti Assortiti', price: '2.00€', allergens: ['gluten', 'eggs', 'milk'] }
        ]
      },
      {
        id: 13,
        name: 'Croissants',
        nameIT: 'Cornetti',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_pasticceria-1024x682.jpg',
        items: [
          { id: 301, name: 'Croissant Plain', nameIT: 'Cornetto Vuoto', price: '1.70€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 302, name: 'Croissant Cream', nameIT: 'Cornetto Crema', price: '1.90€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 303, name: 'Croissant Nutella', nameIT: 'Cornetto Nutella', price: '1.90€', allergens: ['gluten', 'eggs', 'milk', 'nuts'] },
          { id: 304, name: 'Croissant Cream Amarena', nameIT: 'Cornetto Crema Amarena', price: '1.90€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 305, name: 'Croissant Jam', nameIT: 'Cornetto Marmellata', price: '1.90€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 306, name: 'Croissant Pistachio', nameIT: 'Cornetto Pistacchio', price: '2.20€', allergens: ['gluten', 'eggs', 'milk', 'nuts'] },
          { id: 307, name: 'Vegan Croissant Plain', nameIT: 'Cornetto Vegano Vuoto', price: '1.80€', allergens: ['gluten'] },
          { id: 308, name: 'Vegan Croissant Honey', nameIT: 'Cornetto Vegano Miele', price: '1.80€', allergens: ['gluten'] },
          { id: 309, name: 'Vegan Croissant Jam', nameIT: 'Cornetto Vegano Marmellata', price: '2.00€', allergens: ['gluten'] },
          { id: 310, name: '5 Grain Croissant Plain', nameIT: 'Cornetto 5 Cereali Vuoto', price: '1.90€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 311, name: '5 Grain Croissant Berries', nameIT: 'Cornetto 5 Cereali Frutti Bosco', price: '2.10€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 312, name: '5 Grain Croissant Pomegranate', nameIT: 'Cornetto 5 Cereali Melograno', price: '2.10€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 313, name: 'Wholemeal Croissant', nameIT: 'Cornetto Integrale', price: '1.90€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 314, name: 'Croissant Apricot', nameIT: 'Cornetto Albicocca', price: '1.90€', allergens: ['gluten', 'eggs', 'milk'] }
        ]
      }
    ]
  },
  {
    id: 2,
    name: 'Food',
    nameIT: 'Cibo',
    image: 'https://img.qromo.io/businesses/glj0JlFiYPmeSp3-full.jpeg',
    subcategories: [
      {
        id: 21,
        name: 'Fried Delicacies',
        nameIT: 'Frittatine',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_gastronomia-1024x682.jpg',
        items: [
          { id: 401, name: 'Frittatina Provola Peppers', nameIT: 'Frittatina Provola e Peperoni', price: '2.00€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 402, name: 'Frittatina Nerano', nameIT: 'Frittatina alla Nerano', price: '2.00€', description: 'With zucchini and provolone', descriptionIT: 'Con zucchine e provolone', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 403, name: 'Frittatina Porcini', nameIT: 'Frittatina Porcini e Provolone', price: '2.00€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 404, name: 'Frittatina Genovese', nameIT: 'Frittatina alla Genovese', price: '2.00€', description: 'With stewed onions', descriptionIT: 'Con cipolle stufate', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 405, name: 'Frittatina Sausage Friarielli', nameIT: 'Frittatina Salsiccia e Friarielli', price: '2.00€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 406, name: 'Frittatina Margherita', nameIT: 'Frittatina Margherita', price: '1.80€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 407, name: 'Frittatina Ham', nameIT: 'Frittatina Prosciutto', price: '2.00€', allergens: ['gluten', 'eggs', 'milk'] }
        ]
      },
      {
        id: 22,
        name: 'Gastronomy',
        nameIT: 'Gastronomia',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_gastronomia-1024x682.jpg',
        items: [
          { id: 501, name: 'Mini Pizza Margherita', nameIT: 'Mini Pizza Margherita', price: '2.50€', allergens: ['gluten', 'milk', 'sulphites'] },
          { id: 502, name: 'Mini Pizza Ham', nameIT: 'Mini Pizza Prosciutto', price: '3.00€', allergens: ['gluten', 'milk', 'sulphites'] },
          { id: 503, name: 'Mini Pizza Napoli', nameIT: 'Mini Pizza Napoli', price: '3.00€', description: 'With anchovies and capers', descriptionIT: 'Con acciughe e capperi', allergens: ['gluten', 'milk', 'fish', 'sulphites'] },
          { id: 504, name: 'Panino Caprese', nameIT: 'Panino Caprese', price: '4.00€', allergens: ['gluten', 'milk'] },
          { id: 505, name: 'Panino Ham Cheese', nameIT: 'Panino Prosciutto Formaggio', price: '4.00€', allergens: ['gluten', 'milk'] },
          { id: 506, name: 'Panino Mortadella', nameIT: 'Panino Mortadella', price: '3.50€', allergens: ['gluten'] },
          { id: 507, name: 'Toast', nameIT: 'Toast', price: '3.00€', allergens: ['gluten', 'milk'] },
          { id: 508, name: 'Tramezzino', nameIT: 'Tramezzino', price: '2.50€', allergens: ['gluten', 'eggs'] },
          { id: 509, name: 'Octopus Potatoes', nameIT: 'Polipo e Patate Arrosto', price: '8.00€', allergens: ['molluscs'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_gastronomia-1024x682.jpg' },
          { id: 510, name: 'Grouper Millefeuille', nameIT: 'Millefoglie di Cernia', price: '10.00€', allergens: ['fish', 'milk'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/2_gastronomia-1024x682.jpg' },
          { id: 511, name: 'Parmigiana Melanzane', nameIT: 'Parmigiana di Melanzane', price: '7.00€', allergens: ['milk', 'eggs', 'gluten', 'sulphites'] },
          { id: 512, name: 'Mixed Salad', nameIT: 'Insalata Mista', price: '5.00€', allergens: [] }
        ]
      },
      {
        id: 23,
        name: 'English Breakfast',
        nameIT: 'Colazione Inglese',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_food-1-1013x1024.jpg',
        items: [
          { id: 601, name: 'Full English Breakfast', nameIT: 'Full English Breakfast', price: '12.00€', description: 'Eggs, bacon, sausages, beans, mushrooms, tomatoes, toast and tea', descriptionIT: 'Uova, bacon, salsicce, fagioli, funghi, pomodori, pane tostato e tè', allergens: ['gluten', 'eggs', 'milk'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_food-1-1013x1024.jpg' },
          { id: 602, name: 'Eggs Benedict', nameIT: 'Uova alla Benedict', price: '8.00€', allergens: ['gluten', 'eggs', 'milk'] },
          { id: 603, name: 'Scrambled Eggs Toast', nameIT: 'Uova Strapazzate Toast', price: '6.00€', allergens: ['gluten', 'eggs', 'milk'] }
        ]
      }
    ]
  },
  {
    id: 3,
    name: 'Cocktails, Beers & Spirits',
    nameIT: 'Cocktail, Birre e Liquori',
    image: 'https://img.qromo.io/businesses/xKqXA9ChObqmoy6-full.jpeg',
    subcategories: [
      {
        id: 31,
        name: 'Signature Cocktails',
        nameIT: 'Cocktail Signature',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_aperitivi-1024x682.jpg',
        items: [
          { id: 701, name: 'Aspritz', nameIT: 'Aspritz', price: '6.00€', description: 'Homemade bitter with Amalfi citrus, Asprino wine', descriptionIT: 'Bitter artigianale con agrumi costiera, Asprino', allergens: ['sulphites'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_aperitivi-1024x682.jpg' },
          { id: 702, name: 'Royal Maid Cuba', nameIT: 'Royal Maid in Cuba', price: '7.00€', description: 'Gin, lime, peach liqueur, ginger, berry jam', descriptionIT: 'Gin, lime, liquore pesca, zenzero, marmellata', allergens: [], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/2_aperitivi-1024x682.jpg' },
          { id: 703, name: 'Summerwind', nameIT: 'Summerwind', price: '7.00€', description: 'Bacardi rum, lime, mint, cucumber, sparkling wine', descriptionIT: 'Rum Bacardi, lime, menta, cetriolo, spumante', allergens: ['sulphites'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/3_aperitivi-1024x682.jpg' },
          { id: 704, name: 'Smoky Negroni', nameIT: 'Smoky Negroni', price: '8.00€', description: 'Tanqueray gin, Cocchi vermouth, Campari, Laphroaig', descriptionIT: 'Tanqueray gin, vermouth Cocchi, Campari, Laphroaig', allergens: ['sulphites'], image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/4_aperitivi-1024x682.jpg' }
        ]
      },
      {
        id: 32,
        name: 'Classic Cocktails',
        nameIT: 'Cocktail Classici',
        image: 'https://img.qromo.io/businesses/xKqXA9ChObqmoy6-full.jpeg',
        items: [
          { id: 801, name: 'Aperol Spritz', nameIT: 'Aperol Spritz', price: '6.00€', allergens: ['sulphites'] },
          { id: 802, name: 'Mojito', nameIT: 'Mojito', price: '7.00€', allergens: [] },
          { id: 803, name: 'Negroni', nameIT: 'Negroni', price: '7.00€', allergens: ['sulphites'] },
          { id: 804, name: 'Moscow Mule', nameIT: 'Moscow Mule', price: '7.00€', allergens: [] },
          { id: 805, name: 'Gin Tonic', nameIT: 'Gin Tonic', price: '7.00€', allergens: ['sulphites'] },
          { id: 806, name: 'Daiquiri', nameIT: 'Daiquiri', price: '7.00€', allergens: [] },
          { id: 807, name: 'Margarita', nameIT: 'Margarita', price: '7.00€', allergens: [] },
          { id: 808, name: 'Caipirinha', nameIT: 'Caipirinha', price: '6.50€', allergens: [] }
        ]
      },
      {
        id: 33,
        name: 'Beers & Spirits',
        nameIT: 'Birre e Liquori',
        image: 'https://img.qromo.io/businesses/xKqXA9ChObqmoy6-full.jpeg',
        items: [
          { id: 901, name: 'Peroni', nameIT: 'Birra Peroni', price: '4.00€', allergens: ['gluten'] },
          { id: 902, name: 'Nastro Azzurro', nameIT: 'Nastro Azzurro', price: '4.50€', allergens: ['gluten'] },
          { id: 903, name: 'Craft Beer', nameIT: 'Birra Artigianale', price: '5.00€', allergens: ['gluten'] },
          { id: 904, name: 'Heineken', nameIT: 'Heineken', price: '4.50€', allergens: ['gluten'] },
          { id: 905, name: 'Limoncello', nameIT: 'Limoncello', price: '3.50€', allergens: ['sulphites'] },
          { id: 906, name: 'Prosecco', nameIT: 'Prosecco', price: '5.00€', allergens: ['sulphites'] },
          { id: 907, name: 'White Wine', nameIT: 'Vino Bianco', price: '4.00€', allergens: ['sulphites'] },
          { id: 908, name: 'Red Wine', nameIT: 'Vino Rosso', price: '4.00€', allergens: ['sulphites'] },
          { id: 909, name: 'Amaro', nameIT: 'Amaro', price: '3.50€', allergens: [] },
          { id: 910, name: 'Grappa', nameIT: 'Grappa', price: '4.00€', allergens: [] },
          { id: 911, name: 'Whisky', nameIT: 'Whisky', price: '6.00€', allergens: ['gluten'] },
          { id: 912, name: 'Vodka', nameIT: 'Vodka', price: '5.00€', allergens: [] },
          { id: 913, name: 'Rum', nameIT: 'Rum', price: '5.00€', allergens: [] },
          { id: 914, name: 'Gin', nameIT: 'Gin', price: '5.50€', allergens: [] }
        ]
      },
      {
        id: 34,
        name: 'Soft Drinks',
        nameIT: 'Bibite',
        image: 'https://img.qromo.io/businesses/xKqXA9ChObqmoy6-full.jpeg',
        items: [
          { id: 1001, name: 'Coca Cola', nameIT: 'Coca Cola', price: '3.00€', allergens: [] },
          { id: 1002, name: 'Coca Cola Zero', nameIT: 'Coca Cola Zero', price: '3.00€', allergens: [] },
          { id: 1003, name: 'Fanta', nameIT: 'Fanta', price: '3.00€', allergens: [] },
          { id: 1004, name: 'Sprite', nameIT: 'Sprite', price: '3.00€', allergens: [] },
          { id: 1005, name: 'Water', nameIT: 'Acqua Naturale', price: '1.50€', allergens: [] },
          { id: 1006, name: 'Sparkling Water', nameIT: 'Acqua Frizzante', price: '1.50€', allergens: [] },
          { id: 1007, name: 'Fruit Juice', nameIT: 'Succo di Frutta', price: '3.00€', allergens: [] },
          { id: 1008, name: 'Chinotto', nameIT: 'Chinotto', price: '3.00€', allergens: [] }
        ]
      }
    ]
  }
];

export const allergensList = [
  { id: 'gluten', name: 'Gluten', nameIT: 'Glutine', icon: '🌾' },
  { id: 'milk', name: 'Milk', nameIT: 'Latte', icon: '🥛' },
  { id: 'eggs', name: 'Eggs', nameIT: 'Uova', icon: '🥚' },
  { id: 'nuts', name: 'Nuts', nameIT: 'Frutta a guscio', icon: '🌰' },
  { id: 'fish', name: 'Fish', nameIT: 'Pesce', icon: '🐟' },
  { id: 'soy', name: 'Soy', nameIT: 'Soia', icon: '🫘' },
  { id: 'sulphites', name: 'Sulphites', nameIT: 'Solfiti', icon: '🍷' },
  { id: 'crustaceans', name: 'Crustaceans', nameIT: 'Crostacei', icon: '🦐' },
  { id: 'molluscs', name: 'Molluscs', nameIT: 'Molluschi', icon: '🦪' },
  { id: 'celery', name: 'Celery', nameIT: 'Sedano', icon: '🥬' },
  { id: 'mustard', name: 'Mustard', nameIT: 'Senape', icon: '🌭' },
  { id: 'sesame', name: 'Sesame', nameIT: 'Sesamo', icon: '🫚' },
  { id: 'lupin', name: 'Lupin', nameIT: 'Lupini', icon: '🫛' },
  { id: 'peanuts', name: 'Peanuts', nameIT: 'Arachidi', icon: '🥜' }
];

export const allergensInfo = {
  gluten: { descriptionIT: 'Cereali contenenti glutine', descriptionEN: 'Cereals containing gluten' },
  milk: { descriptionIT: 'Latte e derivati', descriptionEN: 'Milk and derivatives' },
  eggs: { descriptionIT: 'Uova e derivati', descriptionEN: 'Eggs and derivatives' },
  nuts: { descriptionIT: 'Frutta a guscio', descriptionEN: 'Nuts' },
  fish: { descriptionIT: 'Pesce', descriptionEN: 'Fish' },
  soy: { descriptionIT: 'Soia', descriptionEN: 'Soy' },
  sulphites: { descriptionIT: 'Solfiti', descriptionEN: 'Sulphites' },
  crustaceans: { descriptionIT: 'Crostacei', descriptionEN: 'Crustaceans' },
  molluscs: { descriptionIT: 'Molluschi', descriptionEN: 'Molluscs' },
  celery: { descriptionIT: 'Sedano', descriptionEN: 'Celery' },
  mustard: { descriptionIT: 'Senape', descriptionEN: 'Mustard' },
  sesame: { descriptionIT: 'Sesamo', descriptionEN: 'Sesame' },
  lupin: { descriptionIT: 'Lupini', descriptionEN: 'Lupin' },
  peanuts: { descriptionIT: 'Arachidi', descriptionEN: 'Peanuts' }
};

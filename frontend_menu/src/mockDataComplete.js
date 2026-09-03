export const menuCategories = [
  // SEZIONE 1: CAFFETTERIA
  {
    id: 1,
    name: 'Coffee Shop',
    nameIT: 'Caffetteria',
    image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_bar-1024x682.jpg',
    items: [
      { 
        id: 101, 
        name: 'Caffè Ceraldi', 
        nameIT: 'Caffè Ceraldi', 
        price: '3.50€', 
        description: 'Chocolate fondue with Ecuadorian dark chocolate, artisan coffee cream, fresh whipped cream',
        descriptionIT: 'Fondo di Cioccolata calda fondente equador, crema di caffè artigianale, panna fresca montata',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/2_bar-1024x682.jpg',
        allergens: ['milk'] 
      },
      { 
        id: 102, 
        name: 'Caffè Viennese', 
        nameIT: 'Caffè Viennese', 
        price: '3.50€', 
        description: 'Espresso, cane sugar cream, Strega Alberti, fresh whipped cream',
        descriptionIT: 'Caffè espresso, crema di zucchero di canna, Strega Alberti, panna fresca montata',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/4_bar-1024x682.jpg',
        allergens: ['milk'] 
      },
      { 
        id: 103, 
        name: 'Caffè CaldoFreddo', 
        nameIT: 'Caffè CaldoFreddo', 
        price: '2.50€', 
        description: 'Espresso with cold frothed milk. Do not stir - experience the contrast between hot coffee and cold milk',
        descriptionIT: 'Caffè espresso, latte montato a freddo. Il caffè non va girato e durante la bevuta si avverte il contrasto tra il caldo del caffè e il freddo del latte',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/3_bar-1024x682.jpg',
        allergens: ['milk'] 
      },
      { 
        id: 104, 
        name: 'Caffè Michelino', 
        nameIT: 'Caffè Michelino', 
        price: '3.00€', 
        description: 'Espresso, cane sugar cream, whipped cream melted in a bain-marie, dusted with cocoa',
        descriptionIT: 'Caffè espresso, crema di zucchero di canna, panna montata e poi sciolta a bagnomaria, spolverata di cacao',
        allergens: ['milk'] 
      },
      { 
        id: 105, 
        name: 'Espresso', 
        nameIT: 'Caffè Espresso', 
        price: '1.20€', 
        allergens: [] 
      },
      { 
        id: 106, 
        name: 'Cappuccino', 
        nameIT: 'Cappuccino', 
        price: '1.50€', 
        allergens: ['milk'] 
      },
      { 
        id: 107, 
        name: 'Caffè Macchiato', 
        nameIT: 'Caffè Macchiato', 
        price: '1.30€', 
        allergens: ['milk'] 
      }
    ]
  },

  // SEZIONE 2: DOLCI / PASTICCERIA
  {
    id: 2,
    name: 'Pastry & Desserts',
    nameIT: 'Pasticceria e Dolci',
    image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_pasticceria-1024x682.jpg',
    items: [
      { 
        id: 201, 
        name: 'Sfogliatella Riccia', 
        nameIT: 'Sfogliatella Riccia', 
        price: '2.00€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/10_pasticceria-1024x682.jpg',
        allergens: ['gluten', 'milk', 'eggs'] 
      },
      { 
        id: 202, 
        name: 'Sfogliatella Frolla', 
        nameIT: 'Sfogliatella Frolla', 
        price: '2.00€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/9_pasticceria-1024x682.jpg',
        allergens: ['gluten', 'milk', 'eggs'] 
      },
      { 
        id: 203, 
        name: 'Sfogliatella Santa Rosa', 
        nameIT: 'Sfogliatella Santa Rosa', 
        price: '2.50€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/11_pasticceria-1024x682.jpg',
        allergens: ['gluten', 'milk', 'eggs', 'nuts'] 
      },
      { 
        id: 204, 
        name: 'Babà', 
        nameIT: 'Babà', 
        price: '2.50€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/7_pasticceria-1024x682.jpg',
        allergens: ['gluten', 'eggs', 'sulphites'] 
      },
      { 
        id: 205, 
        name: 'Babà with Cream and Amarena', 
        nameIT: 'Babà Crema e Amarena', 
        price: '3.50€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/4_pasticceria.jpg',
        allergens: ['gluten', 'eggs', 'milk', 'sulphites'] 
      },
      { 
        id: 206, 
        name: 'Babà with Cream and Strawberry', 
        nameIT: 'Babà Panna e Fragola', 
        price: '3.50€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/2_pasticceria-1024x682.jpg',
        allergens: ['gluten', 'eggs', 'milk', 'sulphites'] 
      },
      { 
        id: 207, 
        name: 'Strawberry Tart', 
        nameIT: 'Crostatina di Fragole', 
        price: '3.00€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_pasticceria-1024x682.jpg',
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 208, 
        name: 'Tiramisù', 
        nameIT: 'Tiramisù', 
        price: '4.00€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/5_pasticceria.jpg',
        allergens: ['eggs', 'milk', 'gluten'] 
      },
      { 
        id: 209, 
        name: 'Berry Cheesecake', 
        nameIT: 'Cheesecake ai Frutti di Bosco', 
        price: '4.50€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/6_pasticceria-1024x681.jpg',
        allergens: ['milk', 'gluten', 'eggs'] 
      },
      { 
        id: 210, 
        name: 'Pan di Stelle Semifreddo', 
        nameIT: 'Semifreddo Pan di Stelle', 
        price: '4.00€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/3_pasticceria-1024x682.jpg',
        allergens: ['milk', 'gluten', 'eggs', 'nuts'] 
      },
      { 
        id: 211, 
        name: 'Zeppola di San Giuseppe', 
        nameIT: 'Zeppola di San Giuseppe', 
        price: '2.50€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/8_pasticceria-1024x682.jpg',
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 212, 
        name: 'Puff Pastry Croissant with Cream', 
        nameIT: 'Cornetto Pasta Sfoglia alla Crema', 
        price: '1.90€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 213, 
        name: 'Puff Pastry Croissant with Nutella', 
        nameIT: 'Cornetto Pasta Sfoglia con Nutella', 
        price: '1.90€', 
        allergens: ['gluten', 'eggs', 'milk', 'nuts'] 
      },
      { 
        id: 214, 
        name: 'Puff Pastry Croissant with Cream and Amarena', 
        nameIT: 'Cornetto Pasta Sfoglia con Crema ed Amarena', 
        price: '1.90€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 215, 
        name: 'Puff Pastry Croissant with Jam', 
        nameIT: 'Cornetto Pasta Sfoglia con Marmellata', 
        price: '1.90€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 216, 
        name: 'Vegan Croissant Plain', 
        nameIT: 'Cornetto Vegano Vuoto', 
        price: '1.80€', 
        allergens: ['gluten'] 
      },
      { 
        id: 217, 
        name: 'Vegan Croissant with Honey', 
        nameIT: 'Cornetto Vegano al Miele', 
        price: '1.80€', 
        allergens: ['gluten'] 
      },
      { 
        id: 218, 
        name: '5 Grain Croissant Plain', 
        nameIT: 'Cornetto ai 5 Cereali Vuoto', 
        price: '1.90€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 219, 
        name: '5 Grain Croissant with Berries', 
        nameIT: 'Cornetto ai 5 Cereali ai Frutti di Bosco', 
        price: '1.90€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 220, 
        name: '5 Grain Croissant with Pomegranate', 
        nameIT: 'Cornetto ai 5 Cereali al Melograno', 
        price: '1.90€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 221, 
        name: 'Neapolitan Pastiera', 
        nameIT: 'Pastiera Napoletana', 
        price: '12.50€', 
        allergens: ['gluten', 'eggs', 'milk', 'nuts'] 
      }
    ]
  },

  // SEZIONE 3: SALATO / GASTRONOMIA
  {
    id: 3,
    name: 'Savory / Gastronomy',
    nameIT: 'Salato / Gastronomia',
    image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_gastronomia-1024x682.jpg',
    items: [
      { 
        id: 301, 
        name: 'Frittatina with Provola and Peppers', 
        nameIT: 'Frittatina Provola e Peperoni', 
        price: '2.00€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 302, 
        name: 'Frittatina alla Nerano', 
        nameIT: 'Frittatina alla Nerano', 
        price: '2.00€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 303, 
        name: 'Frittatina with Porcini and Provolone del Monaco', 
        nameIT: 'Frittatina Porcini e Provolone del Monaco', 
        price: '2.00€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 304, 
        name: 'Frittatina alla Genovese', 
        nameIT: 'Frittatina alla Genovese', 
        price: '2.00€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 305, 
        name: 'Frittatina with Sausage and Friarielli', 
        nameIT: 'Frittatina Salsiccia e Friarielli', 
        price: '2.00€', 
        allergens: ['gluten', 'eggs', 'milk'] 
      },
      { 
        id: 306, 
        name: 'Mini Pizza', 
        nameIT: 'Mini Pizza', 
        price: '2.50€', 
        allergens: ['gluten', 'milk', 'sulphites'] 
      },
      { 
        id: 307, 
        name: 'Sandwiches', 
        nameIT: 'Panini', 
        price: '3.50€', 
        allergens: ['gluten'] 
      },
      { 
        id: 308, 
        name: 'Octopus and Roasted Potatoes', 
        nameIT: 'Polipo e Patate Arrosto', 
        price: '8.00€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_gastronomia-1024x682.jpg',
        allergens: ['molluscs'] 
      },
      { 
        id: 309, 
        name: 'Grouper Millefeuille with Escarole and Melted Provola', 
        nameIT: 'Millefoglie di Cernia con Scarole e Provola Fusa', 
        price: '10.00€',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/2_gastronomia-1024x682.jpg',
        allergens: ['fish', 'milk'] 
      }
    ]
  },

  // SEZIONE 4: COLAZIONE INGLESE
  {
    id: 4,
    name: 'English Breakfast',
    nameIT: 'Colazione Inglese',
    image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_food-1-1013x1024.jpg',
    items: [
      { 
        id: 401, 
        name: 'Full English Breakfast', 
        nameIT: 'Full English Breakfast', 
        price: '12.00€',
        description: 'A rich and varied breakfast prepared according to tradition. Includes: eggs, bacon, sausages, beans, mushrooms, tomatoes, toast and tea',
        descriptionIT: 'Una colazione ricca e varia, preparata come vuole la tradizione. Comprende: uova, bacon, salsicce, fagioli, funghi e pomodori, pane tostato e l\'immancabile tè',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/03/1_food-1-1013x1024.jpg',
        allergens: ['gluten', 'eggs', 'milk'] 
      }
    ]
  },

  // SEZIONE 5: APERITIVI / COCKTAILS
  {
    id: 5,
    name: 'Cocktails & Aperitifs',
    nameIT: 'Cocktail e Aperitivi',
    image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_aperitivi-1024x682.jpg',
    items: [
      { 
        id: 501, 
        name: 'Aspritz', 
        nameIT: 'Aspritz', 
        price: '6.00€',
        description: 'Homemade bitter with Amalfi Coast citrus and herbs, mixed with sparkling Asprino d\'Aversa wine',
        descriptionIT: 'Bitter "home made" caratterizzato dall\'uso di agrumi della costiera Amalfitana e da erbe e radici, miscelato con un Asprino d\'Aversa spumantizzato',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/1_aperitivi-1024x682.jpg',
        allergens: ['sulphites'] 
      },
      { 
        id: 502, 
        name: 'Royal Maid in Cuba', 
        nameIT: 'Royal Maid in Cuba', 
        price: '7.00€',
        description: 'Gin, lime juice, peach liqueur, fresh ginger, berry jam',
        descriptionIT: 'Gin, succo di lime, liquore di pesca, zenzero fresco, marmellata di frutti di bosco',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/2_aperitivi-1024x682.jpg',
        allergens: [] 
      },
      { 
        id: 503, 
        name: 'Summerwind', 
        nameIT: 'Summerwind', 
        price: '7.00€',
        description: 'Bacardi rum, lime juice, absinthe drops, mint, cucumber, sparkling wine',
        descriptionIT: 'Rum Bacardi, succo di lime, gocce di assenzio, menta, cetriolo, spumante',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/3_aperitivi-1024x682.jpg',
        allergens: ['sulphites'] 
      },
      { 
        id: 504, 
        name: 'Smoky Negroni', 
        nameIT: 'Smoky Negroni', 
        price: '8.00€',
        description: 'Tanqueray gin, Cocchi vermouth, Campari bitter, splash of Laphroaig 10y',
        descriptionIT: 'Tanqueray gin, vermouth Cocchi, bitter Campari, splash di Laphraig 10 y',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/4_aperitivi-1024x682.jpg',
        allergens: ['sulphites'] 
      },
      { 
        id: 505, 
        name: 'Aperol Spritz', 
        nameIT: 'Aperol Spritz', 
        price: '6.00€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 506, 
        name: 'Mojito', 
        nameIT: 'Mojito', 
        price: '7.00€', 
        allergens: [] 
      },
      { 
        id: 507, 
        name: 'Peroni Beer', 
        nameIT: 'Birra Peroni', 
        price: '4.00€', 
        allergens: ['gluten'] 
      },
      { 
        id: 508, 
        name: 'Limoncello', 
        nameIT: 'Limoncello', 
        price: '3.50€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 509, 
        name: 'Prosecco', 
        nameIT: 'Prosecco', 
        price: '5.00€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 510, 
        name: 'White Wine', 
        nameIT: 'Vino Bianco', 
        price: '4.00€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 511, 
        name: 'Red Wine', 
        nameIT: 'Vino Rosso', 
        price: '4.00€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 512, 
        name: 'Amaro', 
        nameIT: 'Amaro', 
        price: '3.50€', 
        allergens: [] 
      },
      { 
        id: 513, 
        name: 'Grappa', 
        nameIT: 'Grappa', 
        price: '4.00€', 
        allergens: [] 
      },
      { 
        id: 514, 
        name: 'Whisky', 
        nameIT: 'Whisky', 
        price: '6.00€', 
        allergens: ['gluten'] 
      }
    ]
  }
];

// ... rest of the allergensList and allergensInfo remains the same        description: 'Gin, lime juice, peach liqueur, fresh ginger, berry jam',
        descriptionIT: 'Gin, succo di lime, liquore di pesca, zenzero fresco, marmellata di frutti di bosco',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/2_aperitivi-1024x682.jpg',
        allergens: [] 
      },
      { 
        id: 503, 
        name: 'Summerwind', 
        nameIT: 'Summerwind', 
        price: '7.00€',
        description: 'Bacardi rum, lime juice, absinthe drops, mint, cucumber, sparkling wine',
        descriptionIT: 'Rum Bacardi, succo di lime, gocce di assenzio, menta, cetriolo, spumante',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/3_aperitivi-1024x682.jpg',
        allergens: ['sulphites'] 
      },
      { 
        id: 504, 
        name: 'Smoky Negroni', 
        nameIT: 'Smoky Negroni', 
        price: '8.00€',
        description: 'Tanqueray gin, Cocchi vermouth, Campari bitter, splash of Laphroaig 10y',
        descriptionIT: 'Tanqueray gin, vermouth Cocchi, bitter Campari, splash di Laphraig 10 y',
        image: 'https://ceraldicaffe.it/wp-content/uploads/2019/02/4_aperitivi-1024x682.jpg',
        allergens: ['sulphites'] 
      },
      { 
        id: 505, 
        name: 'Aperol Spritz', 
        nameIT: 'Aperol Spritz', 
        price: '6.00€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 506, 
        name: 'Mojito', 
        nameIT: 'Mojito', 
        price: '7.00€', 
        allergens: [] 
      },
      { 
        id: 507, 
        name: 'Peroni Beer', 
        nameIT: 'Birra Peroni', 
        price: '4.00€', 
        allergens: ['gluten'] 
      },
      { 
        id: 508, 
        name: 'Limoncello', 
        nameIT: 'Limoncello', 
        price: '3.50€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 509, 
        name: 'Prosecco', 
        nameIT: 'Prosecco', 
        price: '5.00€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 510, 
        name: 'White Wine', 
        nameIT: 'Vino Bianco', 
        price: '4.00€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 511, 
        name: 'Red Wine', 
        nameIT: 'Vino Rosso', 
        price: '4.00€', 
        allergens: ['sulphites'] 
      },
      { 
        id: 512, 
        name: 'Amaro', 
        nameIT: 'Amaro', 
        price: '3.50€', 
        allergens: [] 
      },
      { 
        id: 513, 
        name: 'Grappa', 
        nameIT: 'Grappa', 
        price: '4.00€', 
        allergens: [] 
      },
      { 
        id: 514, 
        name: 'Whisky', 
        nameIT: 'Whisky', 
        price: '6.00€', 
        allergens: ['gluten'] 
      }
    ]
  }
];

// ... rest of the allergensList and allergensInfo remains the same
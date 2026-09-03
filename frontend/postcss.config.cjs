module.exports = {
  plugins: {
    // Tailwind produce CSS solo dove ci sono le direttive @tailwind
    // (src/menu/menu.css): il resto dell'app non cambia.
    tailwindcss: {},
    autoprefixer: {},
  },
}

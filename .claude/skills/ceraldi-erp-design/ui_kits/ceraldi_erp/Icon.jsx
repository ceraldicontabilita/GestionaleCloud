/* Shared icon helper for the Ceraldi ERP UI kit.
   Renders a Lucide icon and (re)hydrates it after mount. */
function Icon({ name, size = 16, color = 'currentColor', style = {} }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (ref.current && window.lucide) {
      ref.current.innerHTML = '';
      const el = document.createElement('i');
      el.setAttribute('data-lucide', name);
      ref.current.appendChild(el);
      window.lucide.createIcons({ nameAttr: 'data-lucide', attrs: { width: size, height: size, stroke: color } });
    }
  }, [name, size, color]);
  return <span ref={ref} style={{ display: 'inline-flex', width: size, height: size, ...style }} />;
}

window.Icon = Icon;

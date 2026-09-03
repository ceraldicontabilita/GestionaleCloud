// Primitivi UI della pagina Lotti — estratti 1:1 da LottiList.jsx
// (refactor 25/07/2026). Nessun cambio di stile: stesse classi, stesse
// varianti. `Card` non è ridefinita qui: si riusa quella condivisa in
// shared/Card.jsx, che era già identica carattere per carattere.
export { Card } from "../shared/Card";

export const Button = ({ children, onClick, variant = "primary", size = "md", disabled = false, className = "", ...props }) => {
  const variants = {
    primary: "bg-[#5b7a6b] hover:bg-[#4d6a5c] text-white",
    secondary: "bg-gray-100 hover:bg-gray-200 text-gray-700",
    danger: "bg-red-500 hover:bg-red-600 text-white",
    success: "bg-green-600 hover:bg-green-700 text-white",
    ghost: "hover:bg-gray-100 text-gray-600"
  };
  const sizes = { sm: "px-3 py-1.5 text-sm", md: "px-4 py-2", lg: "px-6 py-3 text-lg" };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg font-medium transition-all duration-200 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
};

export const Input = ({ label, ...props }) => (
  <div className="space-y-1">
    {label && <label className="text-sm font-medium text-gray-700">{label}</label>}
    <input
      className="w-full px-4 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-[#5b7a6b] focus:border-transparent transition-all"
      {...props}
    />
  </div>
);

export const Badge = ({ children, variant = "default" }) => {
  const variants = {
    default: "bg-gray-100 text-gray-700",
    warning: "bg-amber-100 text-amber-700",
    success: "bg-green-100 text-green-700",
    danger: "bg-red-100 text-red-700"
  };
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${variants[variant]}`}>
      {children}
    </span>
  );
};

export const Modal = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-auto">
        <div className="flex items-center justify-between p-3 border-b bg-gray-50 rounded-t-2xl">
          <h2 className="text-lg font-bold text-gray-800">{title}</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            ✕
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
};

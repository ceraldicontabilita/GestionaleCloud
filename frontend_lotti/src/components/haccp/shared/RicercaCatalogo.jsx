import { useRef } from "react";
import { Search, Keyboard } from "lucide-react";

export default function RicercaCatalogo({ value, onChange, placeholder }) {
  const input = useRef(null);
  const chiudiTastiera = () => {
    input.current?.blur();
    navigator.virtualKeyboard?.hide?.();
  };
  return <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
    <div className="relative min-w-[160px] flex-1">
      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
      <input ref={input} type="search" enterKeyHint="search" autoComplete="off"
        aria-label={placeholder} placeholder={placeholder} value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter" || e.key === "Escape") { e.preventDefault(); chiudiTastiera(); } }}
        className="w-full min-h-[44px] rounded-xl border border-gray-200 bg-white py-2 pl-9 pr-3 text-base" />
    </div>
    <button type="button" onClick={chiudiTastiera} className="flex min-h-[44px] items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 text-sm">
      <Keyboard size={16} /> Nascondi tastiera
    </button>
  </div>;
}

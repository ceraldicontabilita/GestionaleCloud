import React from 'react';
import { Cookie, X } from 'lucide-react';

const CookieBanner = ({ onAccept, onDecline }) => {
  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-[#3d4d3d] text-white py-3 px-4 shadow-lg">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Cookie className="w-6 h-6 text-[#d4af37] flex-shrink-0" />
          <p className="text-sm">
            We use the cookies necessary for the operation of the website.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={onDecline}
            className="px-4 py-1.5 rounded-md bg-transparent border border-white text-white hover:bg-white/10 transition-colors text-sm"
          >
            No
          </button>
          <button
            onClick={onAccept}
            className="px-4 py-1.5 rounded-md bg-[#d4af37] text-black font-medium hover:bg-[#c9a332] transition-colors text-sm"
          >
            Ok
          </button>
        </div>
      </div>
    </div>
  );
};

export default CookieBanner;
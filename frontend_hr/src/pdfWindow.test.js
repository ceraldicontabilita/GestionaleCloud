import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apriFinestraPdfAttesa, mostraPdfNellaFinestra } from "./pdfWindow";

describe("finestra PDF autenticato", () => {
  let finestra;

  beforeEach(() => {
    finestra = { opener: {}, closed: false, location: { replace: vi.fn() } };
    vi.stubGlobal("window", { open: vi.fn(() => finestra) });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:pagina-attesa");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("non apre una scheda vuota che può essere ripristinata sulla SPA", () => {
    expect(apriFinestraPdfAttesa()).toBe(finestra);
    expect(window.open).toHaveBeenCalledWith("blob:pagina-attesa", "_blank");
    expect(window.open).not.toHaveBeenCalledWith("", expect.anything());
    expect(finestra.opener).toBeNull();

    vi.runAllTimers();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:pagina-attesa");
  });

  it("sostituisce la pagina di attesa con il PDF e la pagina richiesta", () => {
    expect(mostraPdfNellaFinestra(finestra, "blob:cedolino", 3)).toBe(true);
    expect(finestra.location.replace).toHaveBeenCalledWith("blob:cedolino#page=3");
  });

  it("non tenta la navigazione se il popup è stato bloccato o chiuso", () => {
    expect(mostraPdfNellaFinestra(null, "blob:cedolino")).toBe(false);
    finestra.closed = true;
    expect(mostraPdfNellaFinestra(finestra, "blob:cedolino")).toBe(false);
    expect(finestra.location.replace).not.toHaveBeenCalled();
  });
});

import fs from "fs";
import path from "path";
import vm from "vm";

const html=fs.readFileSync(path.resolve(__dirname,"../../../frontend_colazioni/index.html"),"utf8");
function funzione(nome){const inizio=html.indexOf(`function ${nome}(`);let fine=inizio,livello=0,aperto=false;for(;fine<html.length;fine++){if(html[fine]==="{"){livello++;aperto=true;}if(html[fine]==="}"&&--livello===0&&aperto)break;}return html.slice(inizio,fine+1);}
test("usa come prezzo aggiorna solo i nomi automatici, anche con virgola", () => {
  const ctx=vm.createContext({CE:[{nome:"Colazione da €10",prezzo:10},{nome:"Colazione Vesuvio",prezzo:10}],document:{getElementById:()=>null},ceSumRef:()=>{}});
  vm.runInContext(funzione("ceImpostaPrezzo"),ctx);
  ctx.ceImpostaPrezzo(0,"5,5");ctx.ceImpostaPrezzo(1,5.5);
  expect(ctx.CE[0]).toEqual({nome:"Colazione da €5,50",prezzo:5.5});expect(ctx.CE[1].nome).toBe("Colazione Vesuvio");
});
test("il catalogo B&B contiene tutti i reparti e non inventa prezzi", () => {
  const ctx=vm.createContext({});vm.runInContext(funzione("ceCatalogoCarta"),ctx);
  const carta={menus:[{id:1,n:"Bar"},{id:2,n:"Dolci"},{id:3,n:"Food"}],cats:[{id:1,m:1,n:"Caffetteria"},{id:2,m:2,n:"Pasticceria"},{id:3,m:3,n:"Rosticceria"}],items:Array.from({length:80},(_,i)=>({id:i,c:i%3+1,n:"Prodotto "+i,p:i===79?null:250,on:1,allergeni_menu:["milk"]}))};
  const prodotti=ctx.ceCatalogoCarta(carta);expect(prodotti).toHaveLength(80);expect(new Set(prodotti.map(p=>p.cat)).size).toBe(3);expect(prodotti.find(p=>p.id===79).prezzo).toBeNull();expect(prodotti[0].allergeni).toEqual(["milk"]);
});

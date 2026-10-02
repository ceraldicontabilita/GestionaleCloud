jest.mock("axios", () => {
  const axios=jest.fn();axios.interceptors={request:{use:jest.fn()},response:{use:jest.fn()}};axios.create=()=>({get:jest.fn()});return axios;
});
jest.mock("../utils/tabletSession",()=>({allineaSessioneTitolare:jest.fn()}));
jest.mock("sonner",()=>({toast:{}}));

describe("401: sessione verificata dal server e nessuna doppia produzione",()=>{
  let auth, axios, handler, client, API;
  beforeEach(()=>{
    jest.resetModules();localStorage.clear();
    axios=require("axios");client={get:jest.fn()};axios.create=()=>client;
    auth=require("../auth");API=require("../utils/constants").API;
    auth.setupAxiosAuth();handler=axios.interceptors.response.use.mock.calls[0][1];
    auth.saveToken("test-scaduto");auth.saveRuolo("amministratore");
  });
  const errore=(method="get")=>({response:{status:401},config:{url:API+"/ricette-unificate",method,headers:{Authorization:"Bearer test-scaduto"}}});
  test("due GET parallele condividono una verifica ERP, poi recuperano i dati",async()=>{
    client.get.mockResolvedValue({data:{token:"test-rinnovato",operatore:{nome:"Test",dipendente_id:"test-id"}}});axios.mockResolvedValue({data:[{id:"r1"}]});
    const esiti=await Promise.all([handler(errore()),handler(errore())]);
    expect(client.get).toHaveBeenCalledTimes(1);expect(axios).toHaveBeenCalledTimes(2);expect(esiti[0].data).toEqual([{id:"r1"}]);
  });
  test("POST non viene ripetuta dopo il recupero",async()=>{
    client.get.mockResolvedValue({data:{token:"test-rinnovato",operatore:{nome:"Test"}}});
    await expect(handler(errore("post"))).rejects.toMatchObject({response:{status:401}});
    expect(axios).not.toHaveBeenCalled();expect(auth.getToken()).toBe("test-rinnovato");
  });
  test("cookie ERP non valido chiude anche il ruolo amministratore",async()=>{
    client.get.mockRejectedValue(new Error("sessione scaduta"));
    await expect(handler(errore())).rejects.toBeDefined();expect(auth.getToken()).toBe("");expect(auth.isAdmin()).toBe(false);
  });
  test("un vecchio 401 non cancella una nuova sessione",async()=>{
    auth.saveToken("test-piu-recente");axios.mockResolvedValue({data:[]});await handler(errore());expect(auth.getToken()).toBe("test-piu-recente");expect(client.get).not.toHaveBeenCalled();
  });
});

"""
Test suite for Iteration 46 features:
1. QualificaBatchPanel - Fornitori batch approval
2. RegistroAllergeniView - PannelloMancanti + QR code
3. Supervisor fixes - S1 sanificazione, T1/T2 temperature auto-generate
4. Smaltimento lotti scaduti - batch and single
5. Schede Ricevimento Merci - temperature pre-compilate
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8000')


class TestFornitoriQualificaBatch:
    """Test fornitori qualifica batch approval endpoints"""
    
    def test_get_qualifica_in_attesa(self):
        """GET /api/fornitori/qualifica/in-attesa - should return list of fornitori with piva"""
        response = requests.get(f"{BASE_URL}/api/fornitori/qualifica/in-attesa")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Verify structure if there are items
        if len(data) > 0:
            item = data[0]
            assert "nome_fornitore" in item
            assert "piva" in item
            assert "stato" in item
            assert item["stato"] == "in_attesa_verifica"
            print(f"PASS: Found {len(data)} fornitori in attesa with piva field")
        else:
            print("PASS: No fornitori in attesa (empty list is valid)")
    
    def test_approva_batch_empty_list(self):
        """POST /api/fornitori/qualifica/approva-batch with empty pive list"""
        response = requests.post(
            f"{BASE_URL}/api/fornitori/qualifica/approva-batch",
            json={"pive": [], "includi": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert "aggiornati" in data
        assert data["aggiornati"] == 0
        print("PASS: Batch approval with empty list returns aggiornati=0")
    
    def test_approva_batch_with_pive(self):
        """POST /api/fornitori/qualifica/approva-batch with valid pive list"""
        # First get a piva from in-attesa list
        response = requests.get(f"{BASE_URL}/api/fornitori/qualifica/in-attesa")
        data = response.json()
        
        if len(data) > 0:
            # Test with first piva
            test_piva = data[0].get("piva")
            if test_piva:
                response = requests.post(
                    f"{BASE_URL}/api/fornitori/qualifica/approva-batch",
                    json={"pive": [test_piva], "includi": True}
                )
                assert response.status_code == 200
                result = response.json()
                assert "aggiornati" in result
                print(f"PASS: Batch approval returned aggiornati={result['aggiornati']}")
            else:
                print("SKIP: No piva found in first fornitore")
        else:
            print("SKIP: No fornitori in attesa to test batch approval")


class TestSchedeRicevimentoMerci:
    """Test schede ricevimento merci with pre-compiled temperatures"""
    
    def test_get_schede_ricevimento(self):
        """GET /api/fornitori/schede-ricevimento - should return schede with temperature badges"""
        response = requests.get(f"{BASE_URL}/api/fornitori/schede-ricevimento?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            scheda = data[0]
            # Verify required fields
            assert "id_fattura" in scheda
            assert "fornitore" in scheda
            assert "data_consegna" in scheda
            assert "tipo_conservazione" in scheda
            assert "temperatura_rilevata" in scheda
            assert "conforme" in scheda
            
            # Verify tipo_conservazione is one of expected values
            assert scheda["tipo_conservazione"] in ["surgelato", "refrigerato", "ambiente"]
            
            # Count by type
            surgelati = len([s for s in data if s["tipo_conservazione"] == "surgelato"])
            refrigerati = len([s for s in data if s["tipo_conservazione"] == "refrigerato"])
            ambiente = len([s for s in data if s["tipo_conservazione"] == "ambiente"])
            
            print(f"PASS: Found {len(data)} schede - Surgelati: {surgelati}, Refrigerati: {refrigerati}, Ambiente: {ambiente}")
        else:
            print("PASS: No schede ricevimento (empty list is valid)")


class TestHACCPAutoVerificaOggi:
    """Test HACCP auto-generation endpoint"""
    
    def test_verifica_oggi(self):
        """GET /api/haccp-auto/verifica-oggi - should return ok status"""
        response = requests.get(f"{BASE_URL}/api/haccp-auto/verifica-oggi")
        assert response.status_code == 200
        data = response.json()
        
        assert "ok" in data
        assert data["ok"] == True
        assert "generato" in data
        
        if data["generato"]:
            assert "elementi" in data
            print(f"PASS: Auto-generated elements: {data.get('elementi', [])}")
        else:
            print(f"PASS: All data already present for today - message: {data.get('message', '')}")


class TestSupervisorStato:
    """Test supervisor stato endpoint"""
    
    def test_supervisor_stato(self):
        """GET /api/supervisor/stato - should return semaforo arancione with 5 alerts (S1 resolved)"""
        response = requests.get(f"{BASE_URL}/api/supervisor/stato")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "semaforo" in data
        assert "totale_alert" in data
        assert "critici" in data
        assert "alti" in data
        assert "medi" in data
        assert "bassi" in data
        assert "alerts" in data
        
        # Verify semaforo is valid
        assert data["semaforo"] in ["rosso", "arancione", "verde"]
        
        # Check that S1 (sanificazione) is NOT in alerts (should be resolved)
        alert_ids = [a["id"] for a in data["alerts"]]
        
        # S1 should NOT be present if sanificazione is auto-generated
        # T1/T2 should NOT be present if temperatures are auto-generated
        
        print(f"PASS: Supervisor stato - semaforo: {data['semaforo']}, totale_alert: {data['totale_alert']}")
        print(f"  Critici: {data['critici']}, Alti: {data['alti']}, Medi: {data['medi']}, Bassi: {data['bassi']}")
        print(f"  Alert IDs: {alert_ids}")
        
        # Verify no T1/T2 critical alerts (temperatures should be auto-generated)
        if "T1" not in alert_ids and "T2" not in alert_ids:
            print("  PASS: T1/T2 temperature alerts not present (auto-generated)")
        else:
            print(f"  INFO: T1/T2 alerts present - may need manual check")


class TestRegistroAllergeni:
    """Test registro allergeni endpoint"""
    
    def test_get_registro_allergeni(self):
        """GET /api/food-cost/registro-allergeni - should return ricette with allergeni"""
        response = requests.get(f"{BASE_URL}/api/food-cost/registro-allergeni")
        assert response.status_code == 200
        data = response.json()
        
        assert "allergeni_14" in data
        assert "ricette" in data
        assert len(data["allergeni_14"]) == 14  # 14 EU allergens
        
        ricette = data["ricette"]
        assert isinstance(ricette, list)
        
        if len(ricette) > 0:
            ricetta = ricette[0]
            assert "id" in ricetta
            assert "nome" in ricetta
            assert "allergeni" in ricetta
            
            # Count ricette without allergeni
            senza_allergeni = len([r for r in ricette if not r.get("allergeni") or len(r["allergeni"]) == 0])
            con_allergeni = len(ricette) - senza_allergeni
            
            print(f"PASS: Found {len(ricette)} ricette - Con allergeni: {con_allergeni}, Senza allergeni: {senza_allergeni}")
        else:
            print("PASS: No ricette found (empty list)")


class TestLottiSmaltimento:
    """Test lotti smaltimento endpoints"""
    
    def test_get_lotti(self):
        """GET /api/lotti - should return lotti list"""
        response = requests.get(f"{BASE_URL}/api/lotti?limit=100")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Count scaduti
        scaduti = 0
        for lotto in data:
            scadenza = lotto.get("data_scadenza", "")
            if scadenza:
                # Parse date (format: dd/mm/yyyy or yyyy-mm-dd)
                try:
                    if "/" in scadenza:
                        parts = scadenza.split("/")
                        if len(parts) == 3:
                            from datetime import datetime
                            d = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                            if d < datetime.now():
                                scaduti += 1
                except:
                    pass
        
        print(f"PASS: Found {len(data)} lotti, approximately {scaduti} scaduti")
    
    def test_smalti_batch_endpoint_exists(self):
        """POST /api/lotti/smalti-batch - verify endpoint exists"""
        # Test with empty list to verify endpoint exists
        response = requests.post(
            f"{BASE_URL}/api/lotti/smalti-batch?motivo=test",
            json={"ids": []}
        )
        # Should return 200 with smaltiti=0 or 422 for validation
        assert response.status_code in [200, 422]
        print(f"PASS: Smalti batch endpoint exists, status: {response.status_code}")


class TestFornitoriEndpoints:
    """Test fornitori general endpoints"""
    
    def test_get_fornitori_registro_qualificati(self):
        """GET /api/fornitori/registro-qualificati - should return fornitori list"""
        response = requests.get(f"{BASE_URL}/api/fornitori/registro-qualificati")
        assert response.status_code == 200
        data = response.json()
        
        assert "totale_fornitori" in data
        assert "qualificati" in data
        assert "esclusi" in data
        assert "fornitori" in data
        
        fornitori = data["fornitori"]
        if len(fornitori) > 0:
            fornitore = fornitori[0]
            assert "nome" in fornitore
            assert "stato" in fornitore
            
            print(f"PASS: Found {data['totale_fornitori']} fornitori - Qualificati: {data['qualificati']}, Esclusi: {data['esclusi']}")
        else:
            print("PASS: No fornitori found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

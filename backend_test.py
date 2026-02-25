#!/usr/bin/env python3
"""
OpenClaw-3.0 Backend Test Suite
Comprehensive testing for all API endpoints and database connectivity.
"""

import requests
import time
import asyncio
import pymongo
import os
from typing import Dict, List, Any, Optional
import json
from datetime import datetime

# Configuration
BACKEND_URL = "https://bilancio-patch.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"
TIMEOUT = 10  # seconds
MAX_RESPONSE_TIME = 2  # seconds as required

class TestResults:
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0
        self.errors = []
        
    def add_test(self, name: str, passed: bool, details: str = "", response_time: float = 0):
        self.tests.append({
            "name": name,
            "passed": passed,
            "details": details,
            "response_time": response_time,
            "timestamp": datetime.now().isoformat()
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"{name}: {details}")
    
    def print_summary(self):
        print(f"\n{'='*80}")
        print(f"TEST SUMMARY - OpenClaw-3.0 Backend")
        print(f"{'='*80}")
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"Total Tests: {len(self.tests)}")
        print(f"Success Rate: {(self.passed/len(self.tests)*100):.1f}%" if self.tests else "0%")
        
        if self.errors:
            print(f"\n🔍 ERRORS FOUND:")
            for error in self.errors:
                print(f"  • {error}")

def test_api_endpoint(url: str, method: str = "GET", data: Dict = None, expected_status: int = 200) -> tuple:
    """Test an API endpoint and return (success, response_data, response_time, details)"""
    try:
        start_time = time.time()
        
        if method == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=TIMEOUT)
        else:
            response = requests.request(method, url, json=data, timeout=TIMEOUT)
            
        response_time = time.time() - start_time
        
        if response.status_code != expected_status:
            return False, None, response_time, f"Expected status {expected_status}, got {response.status_code}: {response.text[:200]}"
        
        if response_time > MAX_RESPONSE_TIME:
            return False, None, response_time, f"Response time {response_time:.2f}s exceeds limit of {MAX_RESPONSE_TIME}s"
        
        try:
            json_data = response.json()
            return True, json_data, response_time, "Success"
        except:
            return True, response.text, response_time, "Success (non-JSON response)"
            
    except requests.exceptions.Timeout:
        return False, None, TIMEOUT, f"Request timeout after {TIMEOUT}s"
    except requests.exceptions.RequestException as e:
        return False, None, 0, f"Request failed: {str(e)}"
    except Exception as e:
        return False, None, 0, f"Unexpected error: {str(e)}"

def test_mongodb_connection():
    """Test MongoDB Atlas connection"""
    try:
        mongo_url = os.getenv("MONGO_URL", "mongodb+srv://Ceraldidatabase:Accesso1974.@cluster0.vofh7iz.mongodb.net/?appName=Cluster0")
        client = pymongo.MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        
        # Test database
        db = client.azienda_erp_db
        collections = db.list_collection_names()
        
        # Count total documents
        total_docs = 0
        collection_counts = {}
        for collection_name in collections:
            try:
                count = db[collection_name].count_documents({})
                collection_counts[collection_name] = count
                total_docs += count
            except Exception as e:
                collection_counts[collection_name] = f"Error: {e}"
        
        client.close()
        
        return True, {
            "connected": True,
            "database": "azienda_erp_db",
            "collections": len(collections),
            "collection_names": collections,
            "total_documents": total_docs,
            "collection_counts": collection_counts
        }, 0, "MongoDB connection successful"
        
    except Exception as e:
        return False, None, 0, f"MongoDB connection failed: {str(e)}"

def main():
    print(f"🚀 Starting OpenClaw-3.0 Backend Tests")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Testing started at: {datetime.now().isoformat()}")
    print(f"{'='*80}")
    
    results = TestResults()
    
    # 1. Test basic health check
    print("\n1️⃣  Testing Health Check...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/health")
    results.add_test("Health Check", success, details, resp_time)
    if success:
        print(f"   ✅ Health check passed ({resp_time:.3f}s)")
    else:
        print(f"   ❌ Health check failed: {details}")
    
    # 2. Test MongoDB Connection
    print("\n2️⃣  Testing MongoDB Atlas Connection...")
    success, db_data, resp_time, details = test_mongodb_connection()
    results.add_test("MongoDB Connection", success, details, resp_time)
    if success:
        print(f"   ✅ MongoDB connected ({db_data['total_documents']:,} total documents)")
        print(f"   📊 Found {db_data['collections']} collections")
        
        # Check if we have the expected ~94,088 documents
        if db_data['total_documents'] >= 90000:
            results.add_test("Document Count Check", True, f"Found {db_data['total_documents']:,} documents (≥90k)")
            print(f"   ✅ Document count looks good: {db_data['total_documents']:,}")
        else:
            results.add_test("Document Count Check", False, f"Only {db_data['total_documents']:,} documents, expected ~94,088")
            print(f"   ⚠️  Lower document count than expected: {db_data['total_documents']:,}")
        
        # Check if 'suppliers' collection exists
        if 'suppliers' in db_data['collection_names']:
            supplier_count = db_data['collection_counts'].get('suppliers', 0)
            results.add_test("Suppliers Collection", True, f"Found 'suppliers' collection with {supplier_count} documents")
            print(f"   ✅ Suppliers collection exists: {supplier_count} suppliers")
        else:
            results.add_test("Suppliers Collection", False, "Collection 'suppliers' not found")
            print(f"   ❌ Suppliers collection missing")
    else:
        print(f"   ❌ MongoDB connection failed: {details}")
    
    # 3. Test GET /api/suppliers (expect 316 suppliers)
    print("\n3️⃣  Testing GET /api/suppliers...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/suppliers")
    if success and data:
        suppliers_count = len(data) if isinstance(data, list) else 0
        if suppliers_count == 316:
            results.add_test("Suppliers Count (316)", True, f"Found exactly 316 suppliers", resp_time)
            print(f"   ✅ Found exactly 316 suppliers ({resp_time:.3f}s)")
        elif suppliers_count > 0:
            results.add_test("Suppliers Count (316)", False, f"Found {suppliers_count} suppliers, expected 316", resp_time)
            print(f"   ⚠️  Found {suppliers_count} suppliers, expected 316 ({resp_time:.3f}s)")
        else:
            results.add_test("Suppliers Count (316)", False, "No suppliers returned", resp_time)
            print(f"   ❌ No suppliers returned")
        
        # Check supplier data structure
        if isinstance(data, list) and len(data) > 0:
            supplier = data[0]
            required_fields = ['ragione_sociale', 'partita_iva']
            missing_fields = [field for field in required_fields if field not in supplier and f"{field}" not in str(supplier)]
            
            if not missing_fields:
                results.add_test("Supplier Data Structure", True, "Required fields present", resp_time)
                print(f"   ✅ Supplier data structure valid (has ragione_sociale, partita_iva)")
            else:
                results.add_test("Supplier Data Structure", False, f"Missing fields: {missing_fields}", resp_time)
                print(f"   ❌ Missing required fields: {missing_fields}")
                print(f"   📄 Sample supplier keys: {list(supplier.keys())[:10]}")
    else:
        results.add_test("GET /api/suppliers", success, details, resp_time)
        print(f"   ❌ Failed: {details}")
    
    # 4. Test GET /api/suppliers?limit=10 (expect first 10 suppliers)
    print("\n4️⃣  Testing GET /api/suppliers?limit=10...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/suppliers?limit=10")
    if success and data:
        suppliers_count = len(data) if isinstance(data, list) else 0
        if suppliers_count == 10:
            results.add_test("Suppliers Limit=10", True, f"Returned exactly 10 suppliers", resp_time)
            print(f"   ✅ Limit parameter works: returned 10 suppliers ({resp_time:.3f}s)")
        else:
            results.add_test("Suppliers Limit=10", False, f"Returned {suppliers_count} suppliers, expected 10", resp_time)
            print(f"   ❌ Limit parameter issue: returned {suppliers_count} suppliers")
    else:
        results.add_test("Suppliers Limit=10", success, details, resp_time)
        print(f"   ❌ Failed: {details}")
    
    # 5. Test GET /api/invoices
    print("\n5️⃣  Testing GET /api/invoices...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/invoices")
    if success:
        if isinstance(data, list):
            invoice_count = len(data)
            results.add_test("GET /api/invoices", True, f"Returned {invoice_count} invoices", resp_time)
            print(f"   ✅ Invoices endpoint works: {invoice_count} invoices ({resp_time:.3f}s)")
            
            # Check invoice data structure if available
            if invoice_count > 0:
                invoice = data[0]
                print(f"   📄 Sample invoice keys: {list(invoice.keys())[:10]}")
        else:
            results.add_test("GET /api/invoices", True, f"Non-list response: {type(data)}", resp_time)
            print(f"   ✅ Invoices endpoint responded ({resp_time:.3f}s) - non-list response")
    else:
        results.add_test("GET /api/invoices", success, details, resp_time)
        print(f"   ❌ Failed: {details}")
    
    # 6. Test suppliers stats endpoint
    print("\n6️⃣  Testing GET /api/suppliers/stats...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/suppliers/stats")
    if success and data:
        results.add_test("Suppliers Stats", True, f"Stats available: {data}", resp_time)
        print(f"   ✅ Suppliers stats work ({resp_time:.3f}s)")
        if isinstance(data, dict):
            total = data.get('totale', 0)
            active = data.get('attivi', 0)
            print(f"   📊 Total: {total}, Active: {active}")
    else:
        results.add_test("Suppliers Stats", success, details, resp_time)
        print(f"   ❌ Failed: {details}")
    
    # 7. Test search functionality
    print("\n7️⃣  Testing Suppliers Search...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/suppliers?search=test&limit=5")
    results.add_test("Suppliers Search", success, details, resp_time)
    if success:
        search_count = len(data) if isinstance(data, list) else 0
        print(f"   ✅ Search works: {search_count} results ({resp_time:.3f}s)")
    else:
        print(f"   ❌ Search failed: {details}")
    
    # 8. Test ping endpoint
    print("\n8️⃣  Testing Ping Endpoint...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/ping")
    results.add_test("Ping Endpoint", success, details, resp_time)
    if success:
        print(f"   ✅ Ping works ({resp_time:.3f}s)")
    else:
        print(f"   ❌ Ping failed: {details}")
    
    # 9. Test system status
    print("\n9️⃣  Testing System Lock Status...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/system/lock-status")
    results.add_test("System Lock Status", success, details, resp_time)
    if success and data:
        print(f"   ✅ System status available ({resp_time:.3f}s)")
        if isinstance(data, dict):
            email_locked = data.get('email_locked', False)
            print(f"   🔒 Email operations locked: {email_locked}")
    else:
        print(f"   ❌ System status failed: {details}")
    
    # 10. Test error handling with invalid endpoint
    print("\n🔟 Testing Error Handling...")
    success, data, resp_time, details = test_api_endpoint(f"{API_BASE}/nonexistent-endpoint", expected_status=404)
    results.add_test("Error Handling (404)", success, details, resp_time)
    if success:
        print(f"   ✅ 404 handling works ({resp_time:.3f}s)")
    else:
        print(f"   ❌ Error handling issue: {details}")
    
    # Final Results
    results.print_summary()
    
    # Check critical success criteria
    critical_tests = [
        "Health Check", 
        "MongoDB Connection", 
        "GET /api/suppliers",
        "Suppliers Limit=10",
        "GET /api/invoices"
    ]
    
    critical_passed = sum(1 for test in results.tests if test['name'] in critical_tests and test['passed'])
    critical_total = len(critical_tests)
    
    print(f"\n🎯 CRITICAL TESTS: {critical_passed}/{critical_total} passed")
    
    if critical_passed == critical_total:
        print("✅ ALL CRITICAL TESTS PASSED - Backend is stable and working!")
    else:
        print("❌ SOME CRITICAL TESTS FAILED - Backend needs attention!")
    
    print(f"\n🕒 Testing completed at: {datetime.now().isoformat()}")
    
    # Return results for programmatic access
    return results

if __name__ == "__main__":
    results = main()
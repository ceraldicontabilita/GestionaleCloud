import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import CartaPubblica from "./pages/CartaPubblica";
import InformativaPage from "./pages/InformativaPage";
import AdminLoginPage from "./pages/AdminLoginPage";
import AdminDashboard from "./pages/AdminDashboard";
import OrdersPage from "./pages/admin/OrdersPage";
import CounterPage from "./pages/admin/CounterPage";
import KitchenMonitorPage from "./pages/admin/KitchenMonitorPage";
import WarehousePage from "./pages/admin/WarehousePage";
import SalePage from "./pages/admin/SalePage";
import { Toaster } from "./components/ui/toaster";
import { MenuProvider } from "./context/MenuContext";

function App() {
  return (
    <div className="App">
      <MenuProvider>
          <BrowserRouter basename={process.env.PUBLIC_URL || ''}>
            <Routes>
              <Route path="/" element={<CartaPubblica />} />
              <Route path="/privacy" element={<InformativaPage tipo="privacy" />} />
              <Route path="/cookie" element={<InformativaPage tipo="cookie" />} />
              <Route path="/admin/login" element={<AdminLoginPage />} />
              <Route path="/admin" element={<AdminDashboard />} />
              <Route path="/admin/ordini" element={<OrdersPage />} />
              <Route path="/admin/cassa" element={<CounterPage />} />
              <Route path="/admin/cucina" element={<KitchenMonitorPage />} />
              <Route path="/admin/magazzino" element={<WarehousePage />} />
              <Route path="/admin/sale" element={<SalePage />} />
            </Routes>
          </BrowserRouter>
          <Toaster />
      </MenuProvider>
    </div>
  );
}

export default App;

import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import AdminLoginPage from "./pages/AdminLoginPage";
import AdminQRCodePage from "./pages/AdminQRCodePage";
import AdminDashboard from "./pages/AdminDashboard";
import OrdersPage from "./pages/admin/OrdersPage";
import CounterPage from "./pages/admin/CounterPage";
import KitchenMonitorPage from "./pages/admin/KitchenMonitorPage";
import WarehousePage from "./pages/admin/WarehousePage";
import SalePage from "./pages/admin/SalePage";
import { Toaster } from "./components/ui/toaster";
import { MenuProvider } from "./context/MenuContext";
import { CartProvider } from "./context/CartContext";

function App() {
  return (
    <div className="App">
      <MenuProvider>
        <CartProvider>
          <BrowserRouter basename={process.env.PUBLIC_URL || ''}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/admin/login" element={<AdminLoginPage />} />
              <Route path="/admin" element={<AdminDashboard />} />
              <Route path="/admin/qrcode" element={<AdminQRCodePage />} />
              <Route path="/admin/ordini" element={<OrdersPage />} />
              <Route path="/admin/cassa" element={<CounterPage />} />
              <Route path="/admin/cucina" element={<KitchenMonitorPage />} />
              <Route path="/admin/magazzino" element={<WarehousePage />} />
              <Route path="/admin/sale" element={<SalePage />} />
            </Routes>
          </BrowserRouter>
          <Toaster />
        </CartProvider>
      </MenuProvider>
    </div>
  );
}

export default App;

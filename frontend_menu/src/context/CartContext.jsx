import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;
const CART_STORAGE_KEY = 'ceraldi_cart';
const LAST_ORDER_KEY = 'ceraldi_last_order_id';

const CartContext = createContext(null);

export const CartProvider = ({ children }) => {
  const [items, setItems] = useState(() => {
    try {
      const saved = localStorage.getItem(CART_STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [lastOrderId, setLastOrderId] = useState(() => {
    try {
      return localStorage.getItem(LAST_ORDER_KEY) || null;
    } catch {
      return null;
    }
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
    } catch {
      // storage non disponibile, ignoriamo
    }
  }, [items]);

  const addItem = useCallback((product) => {
    setItems((prev) => {
      const existing = prev.find((i) => i.product_id === product.id);
      if (existing) {
        return prev.map((i) =>
          i.product_id === product.id ? { ...i, quantity: i.quantity + 1 } : i
        );
      }
      return [
        ...prev,
        {
          product_id: product.id,
          name: product.nameIT || product.name,
          price: product.price,
          quantity: 1,
          note: ''
        }
      ];
    });
  }, []);

  const updateQuantity = useCallback((product_id, quantity) => {
    setItems((prev) => {
      if (quantity <= 0) {
        return prev.filter((i) => i.product_id !== product_id);
      }
      return prev.map((i) => (i.product_id === product_id ? { ...i, quantity } : i));
    });
  }, []);

  const removeItem = useCallback((product_id) => {
    setItems((prev) => prev.filter((i) => i.product_id !== product_id));
  }, []);

  const clearCart = useCallback(() => {
    setItems([]);
  }, []);

  const itemCount = items.reduce((sum, i) => sum + i.quantity, 0);

  const total = items.reduce((sum, i) => {
    const priceNum = parseFloat(String(i.price).replace('€', '').trim().replace(',', '.')) || 0;
    return sum + priceNum * i.quantity;
  }, 0);

  const submitOrder = useCallback(async ({ table, customerName, note, salaId, numeroCoperti, paymentMethod }) => {
    setSubmitting(true);
    try {
      const response = await axios.post(`${BACKEND_URL}/api/orders/`, {
        items,
        table,
        customer_name: customerName,
        note,
        source: 'cliente',
        sala_id: salaId || null,
        numero_coperti: numeroCoperti || null,
        payment_method: paymentMethod || null
      });
      const orderId = response.data.id;
      setLastOrderId(orderId);
      try {
        localStorage.setItem(LAST_ORDER_KEY, orderId);
      } catch {
        // ignore
      }
      setItems([]);
      return response.data;
    } finally {
      setSubmitting(false);
    }
  }, [items]);

  const value = {
    items,
    itemCount,
    total,
    addItem,
    updateQuantity,
    removeItem,
    clearCart,
    submitOrder,
    submitting,
    lastOrderId
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
};

export const useCart = () => {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
};

export default CartContext;

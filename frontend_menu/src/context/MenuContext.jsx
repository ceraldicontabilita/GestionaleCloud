import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const MenuContext = createContext(null);

export const MenuProvider = ({ children }) => {
  const [menuCategories, setMenuCategories] = useState([]);
  const [allergensList, setAllergensList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadMenuData();
  }, []);

  const loadMenuData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await axios.get(`${BACKEND_URL}/api/menu/`);
      
      setMenuCategories(response.data.categories || []);
      setAllergensList(response.data.allergens || []);
    } catch (err) {
      console.error('Failed to load menu data:', err);
      setError('Failed to load menu data');
      // Fallback to empty arrays
      setMenuCategories([]);
      setAllergensList([]);
    } finally {
      setLoading(false);
    }
  };

  const refreshMenu = () => {
    loadMenuData();
  };

  const value = {
    menuCategories,
    allergensList,
    loading,
    error,
    refreshMenu
  };

  return (
    <MenuContext.Provider value={value}>
      {children}
    </MenuContext.Provider>
  );
};

export const useMenu = () => {
  const context = useContext(MenuContext);
  if (!context) {
    throw new Error('useMenu must be used within a MenuProvider');
  }
  return context;
};

export default MenuContext;

import { createContext, useState, useEffect, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';

// Define the shape of the context data
interface AuthContextType {
  token: string | null;
  user: { email: string; role: string } | null;
  login: (token: string) => Promise<void>;
  logout: () => void;
}

// Create the context
export const AuthContext = createContext<AuthContextType | null>(null);

// Create the provider component
export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [user, setUser] = useState<{ email: string; role: string } | null>(null);
  const navigate = useNavigate();

  const fetchUser = async () => {
    if (token) {
      try {
        const response = await axiosClient.get('/users/me');
        setUser(response.data);
      } catch (error) {
        console.error('Failed to fetch user', error);
        logout(); // Token is invalid, so log out
      }
    }
  };
  
  // Fetch user data when token changes
  useEffect(() => {
    if (token) {
        fetchUser();
    }
  }, [token]);

  const login = async (newToken: string) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
    await fetchUser(); // Fetch user right after login
    navigate('/deliveries');
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
    navigate('/login');
  };

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
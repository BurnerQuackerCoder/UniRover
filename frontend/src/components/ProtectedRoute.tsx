import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

interface ProtectedRouteProps {
  adminOnly?: boolean;
}

const ProtectedRoute = ({ adminOnly = false }: ProtectedRouteProps) => {
  const { token, user } = useAuth();

  if (!token) {
    // User not logged in, redirect to login
    return <Navigate to="/login" replace />;
  }

  if (adminOnly && user?.role !== 'admin') {
    // Logged in user is not admin, redirect to their dashboard
    return <Navigate to="/deliveries" replace />;
  }

  return <Outlet />; // User is authenticated and authorized, render the child route
};

export default ProtectedRoute;
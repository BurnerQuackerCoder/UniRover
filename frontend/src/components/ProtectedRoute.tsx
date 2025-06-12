import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

interface ProtectedRouteProps {
  adminOnly?: boolean;
}

const ProtectedRoute = ({ adminOnly = false }: ProtectedRouteProps) => {
  const { token, user, isLoading } = useAuth();

  // 1. First, wait for the authentication status to be determined.
  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <p>Loading...</p>
      </div>
    );
  }

  // 2. If not loading, check for a valid token.
  if (!token) {
    return <Navigate to="/login" replace />;
  }

  // 3. If it's an admin-only route, check the user's role.
  if (adminOnly && user?.role !== 'admin') {
    return <Navigate to="/deliveries" replace />;
  }
  
  // 4. If all checks pass, render the requested page.
  return <Outlet />;
};

export default ProtectedRoute;
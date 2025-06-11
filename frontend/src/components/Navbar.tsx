import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const Navbar = () => {
  const { token, user, logout } = useAuth();

  return (
    <nav className="bg-white shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center">
            <Link to="/" className="text-2xl font-bold text-blue-600">
              UniRover
            </Link>
          </div>
          <div className="flex items-center space-x-4">
            {token ? (
              <>
                <Link to="/deliveries" className="text-gray-700 hover:text-blue-600 font-medium">
                  My Deliveries
                </Link>
                {user?.role === 'admin' && (
                   <Link to="/admin/dashboard" className="text-gray-700 hover:text-blue-600 font-medium">
                    Admin Dashboard
                  </Link>
                )}
                <span className="text-gray-600">Welcome, {user?.email}</span>
                <button onClick={logout} className="text-white bg-blue-600 hover:bg-blue-700 px-3 py-2 rounded-md text-sm font-medium">
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="text-gray-700 bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded-md text-sm font-medium">
                  Login
                </Link>
                <Link to="/signup" className="text-white bg-blue-600 hover:bg-blue-700 px-3 py-2 rounded-md text-sm font-medium">
                  Sign Up
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
import { Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import UserDashboardPage from './pages/UserDashboardPage';
import AdminDashboardPage from './pages/AdminDashboardPage';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          {/* Public Routes */}
          <Route index element={<HomePage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="signup" element={<SignupPage />} />

          {/* Protected User Route */}
          <Route element={<ProtectedRoute />}>
            <Route path="deliveries" element={<UserDashboardPage />} />
          </Route>
          
          {/* Protected Admin Route */}
          <Route element={<ProtectedRoute adminOnly={true} />}>
            <Route path="admin/dashboard" element={<AdminDashboardPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}

export default App;
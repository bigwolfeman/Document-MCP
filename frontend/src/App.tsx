import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MainApp } from './pages/MainApp';
import { Login } from './pages/Login';
import { Settings } from './pages/Settings';
import { isAuthenticated } from './services/auth';
import './App.css';

// Protected route wrapper
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <Settings />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

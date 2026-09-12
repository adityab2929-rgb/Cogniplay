import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import Navbar from './components/Navbar';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import GameFlow from './pages/GameFlow';
import Results from './pages/Results';
import ParentDashboard from './dashboard/ParentDashboard';
import TeacherDashboard from './dashboard/TeacherDashboard';
import { isLoggedIn } from './utils/api';

/** Gate for dashboard routes. Gameplay is deliberately left open. */
function Protected({ children }) {
  return isLoggedIn() ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Open on purpose: a child plays on a shared classroom device. */}
        <Route path="/play" element={<GameFlow />} />
        <Route path="/results" element={<Results />} />

        <Route path="/parent" element={<Protected><ParentDashboard /></Protected>} />
        <Route path="/teacher" element={<Protected><TeacherDashboard /></Protected>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { getCurrentUser, logout, isLoggedIn } from '../utils/api';

export default function Navbar() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = getCurrentUser();

  // The games are full-screen experiences - chrome would only distract.
  if (location.pathname.startsWith('/play')) return null;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <nav className="bg-white border-b border-slate-200 sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 font-extrabold text-xl text-indigo-600">
          <span className="text-2xl">🧩</span> CogniPlay
        </Link>

        <div className="flex items-center gap-4 text-sm">
          {isLoggedIn() ? (
            <>
              {user?.role === 'teacher' && (
                <Link to="/teacher" className="text-slate-600 hover:text-indigo-600 font-semibold">
                  Class
                </Link>
              )}
              {user?.role === 'parent' && (
                <Link to="/parent" className="text-slate-600 hover:text-indigo-600 font-semibold">
                  My Child
                </Link>
              )}
              <span className="text-slate-400 hidden sm:inline">{user?.name}</span>
              <button
                onClick={handleLogout}
                className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 font-semibold text-slate-700"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="text-slate-600 hover:text-indigo-600 font-semibold">
                Log in
              </Link>
              <Link
                to="/register"
                className="px-4 py-2 rounded-lg bg-indigo-600 text-white font-semibold hover:bg-indigo-700"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

/**
 * Axios client for the Express backend.
 *
 * Attaches the JWT from localStorage to every request and bounces the user to
 * /login on a 401.
 */
import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:3001';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  // The AI service does real feature extraction; give it room before timing out.
  timeout: 120000,
});

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('cogniplay_token');
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('cogniplay_token');
      localStorage.removeItem('cogniplay_user');
      if (window.location.pathname !== '/login') window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

/* ------------------------------------------------------------------ auth -- */

export async function register({ name, email, password, role }) {
  const { data } = await api.post('/api/auth/register', { name, email, password, role });
  persistSession(data);
  return data;
}

export async function login({ email, password }) {
  const { data } = await api.post('/api/auth/login', { email, password });
  persistSession(data);
  return data;
}

export function logout() {
  localStorage.removeItem('cogniplay_token');
  localStorage.removeItem('cogniplay_user');
}

export function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('cogniplay_user'));
  } catch {
    return null;
  }
}

export function isLoggedIn() {
  return Boolean(localStorage.getItem('cogniplay_token'));
}

function persistSession({ token, user }) {
  if (token) localStorage.setItem('cogniplay_token', token);
  if (user) localStorage.setItem('cogniplay_user', JSON.stringify(user));
}

/* --------------------------------------------------------------- children -- */

export async function addChild({ name, age, gender }) {
  const { data } = await api.post('/api/child/add', { name, age, gender });
  return data;
}

export async function getChild(id) {
  const { data } = await api.get(`/api/child/${id}`);
  return data;
}

export async function getAllChildren() {
  const { data } = await api.get('/api/children/all');
  return data;
}

/* -------------------------------------------------------- game submission -- */

/**
 * Submit a completed 4-game session for AI analysis.
 * @param {object} sessionPayload  the Section-14 session JSON
 */
export async function submitGame(sessionPayload) {
  const { data } = await api.post('/api/submit-game', sessionPayload);
  return data;
}

/* ---------------------------------------------------------------- reports -- */

export async function getReport(childId) {
  const { data } = await api.get(`/api/report/${childId}`);
  return data;
}

/** Absolute URL for a session's generated PDF report. */
export function reportPdfUrl(sessionId) {
  return `${BASE_URL}/api/report/pdf/${sessionId}`;
}

export default api;

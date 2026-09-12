/**
 * Firebase Realtime Database - live game event logging.
 *
 * Degrades gracefully: if Firebase env vars are missing (or the network is
 * down), logging falls back to an in-memory buffer so the games keep working
 * and the final session payload is still complete.
 */
import { initializeApp } from 'firebase/app';
import { getDatabase, ref, push, serverTimestamp } from 'firebase/database';

const config = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  databaseURL: process.env.REACT_APP_FIREBASE_DATABASE_URL,
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
};

// Treat the placeholder shipped in .env.example as "not configured".
const isConfigured =
  Boolean(config.apiKey) &&
  Boolean(config.databaseURL) &&
  !config.apiKey.startsWith('your_');

let db = null;

if (isConfigured) {
  try {
    db = getDatabase(initializeApp(config));
  } catch (err) {
    console.warn('[firebase] init failed, using local buffer:', err.message);
  }
} else {
  console.info('[firebase] not configured - events buffered locally only.');
}

/** In-memory mirror of every event, keyed `${childId}/${game}`. */
const localBuffer = {};

/**
 * Log one gameplay event. Fire-and-forget; never throws into game code.
 * Writes to /sessions/{childId}/{game}/events and always mirrors locally.
 */
export function logGameEvent(childId, game, eventData) {
  const event = { ...eventData, timestamp: eventData.timestamp ?? Date.now() };

  const key = childId + '/' + game;
  if (!localBuffer[key]) localBuffer[key] = [];
  localBuffer[key].push(event);

  if (db) {
    // A failed write must never interrupt a 4-year-old's game.
    push(ref(db, 'sessions/' + childId + '/' + game + '/events'), {
      ...event,
      serverTime: serverTimestamp(),
    }).catch((err) => console.warn('[firebase] write failed:', err.message));
  }

  return event;
}

/** Every buffered event for a child+game, used to build the session payload. */
export function getBufferedEvents(childId, game) {
  return localBuffer[childId + '/' + game] || [];
}

/** Aggregate eye-tracking summary across all games for this child. */
export function summariseGaze(childId) {
  const games = ['letter_land', 'number_ninja', 'butterfly_game', 'shape_tracer'];
  const gazes = games
    .flatMap((g) => getBufferedEvents(childId, g))
    .filter((e) => e.type === 'gaze');

  if (gazes.length === 0) {
    return {
      available: false,
      total_fixations: 0,
      avg_fixation_duration_ms: 0,
      off_screen_count: 0,
      gaze_efficiency: 0,
    };
  }

  const durations = gazes.map((g) => g.fixation_duration || 0);
  const offScreen = gazes.filter(
    (g) =>
      g.gaze_x == null ||
      g.gaze_y == null ||
      g.gaze_x < 0 ||
      g.gaze_y < 0 ||
      g.gaze_x > window.innerWidth ||
      g.gaze_y > window.innerHeight
  ).length;

  return {
    available: true,
    total_fixations: gazes.length,
    avg_fixation_duration_ms: Math.round(
      durations.reduce((a, b) => a + b, 0) / durations.length
    ),
    off_screen_count: offScreen,
    gaze_efficiency: Number((1 - offScreen / gazes.length).toFixed(3)),
  };
}

/** Clear the buffer for a child - call when a fresh session starts. */
export function clearBuffer(childId) {
  Object.keys(localBuffer)
    .filter((k) => k.startsWith(childId + '/'))
    .forEach((k) => delete localBuffer[k]);
}

export { db, isConfigured };
export default { logGameEvent, getBufferedEvents, summariseGaze, clearBuffer, isConfigured };

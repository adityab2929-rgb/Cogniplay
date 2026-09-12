/**
 * WebGazer.js eye tracking.
 *
 * Loaded from CDN on demand. Every function is safe to call when no camera /
 * no permission exists — gaze values simply become null and the games continue
 * unaffected. Nothing here ever throws into game code.
 */
import { logGameEvent } from './firebase';

const WEBGAZER_CDN = 'https://webgazer.cs.brown.edu/webgazer.js';
const GAZE_LOG_INTERVAL_MS = 500;

let webgazer = null;
let available = false;
let currentGaze = { x: null, y: null };
let lastGaze = { x: null, y: null, t: 0 };
let fixationStart = 0;
let logTimer = null;
let scriptPromise = null;

/** Inject the WebGazer script tag once; resolves with window.webgazer. */
function loadScript() {
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise((resolve, reject) => {
    if (window.webgazer) return resolve(window.webgazer);

    const tag = document.createElement('script');
    tag.src = WEBGAZER_CDN;
    tag.async = true;
    tag.onload = () => resolve(window.webgazer);
    tag.onerror = () => reject(new Error('WebGazer script failed to load'));
    document.head.appendChild(tag);
  });

  return scriptPromise;
}

/**
 * Start eye tracking for a session.
 *
 * @param {string} childId
 * @param {string} game  game key, attached to every gaze event
 * @returns {Promise<boolean>} true if tracking is live, false if unavailable
 */
export async function initEyeTracking(childId, game) {
  try {
    // A missing mediaDevices API means an insecure origin or no camera at all.
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Camera API unavailable');
    }

    webgazer = await loadScript();
    if (!webgazer) throw new Error('WebGazer unavailable');

    await webgazer
      .setRegression('ridge')
      .setGazeListener((data) => {
        if (!data) return;
        currentGaze = { x: Math.round(data.x), y: Math.round(data.y) };
      })
      .begin();

    // Keep the debug overlays off — they terrify small children.
    webgazer.showVideoPreview(false).showPredictionPoints(false).showFaceOverlay(false);

    available = true;
    fixationStart = Date.now();

    logTimer = setInterval(() => {
      if (currentGaze.x == null) return;

      const now = Date.now();
      const moved =
        lastGaze.x == null ||
        Math.hypot(currentGaze.x - lastGaze.x, currentGaze.y - lastGaze.y) > 40;

      // A fixation ends when the gaze jumps beyond the 40px dispersion threshold.
      const fixationDuration = moved ? now - fixationStart : now - fixationStart;
      if (moved) fixationStart = now;

      logGameEvent(childId, game, {
        type: 'gaze',
        gaze_x: currentGaze.x,
        gaze_y: currentGaze.y,
        fixation_duration: fixationDuration,
        game,
      });

      lastGaze = { ...currentGaze, t: now };
    }, GAZE_LOG_INTERVAL_MS);

    return true;
  } catch (err) {
    console.info('[eyeTracking] unavailable, continuing without gaze:', err.message);
    available = false;
    currentGaze = { x: null, y: null };
    return false;
  }
}

/** Stop tracking and release the camera. Safe to call when never started. */
export function stopEyeTracking() {
  if (logTimer) {
    clearInterval(logTimer);
    logTimer = null;
  }
  try {
    if (webgazer && available) {
      webgazer.clearGazeListener();
      webgazer.pause();
      webgazer.end();
    }
  } catch (err) {
    console.warn('[eyeTracking] shutdown warning:', err.message);
  }
  available = false;
  currentGaze = { x: null, y: null };
}

/** Current gaze point. Returns {x:null,y:null} when tracking is off. */
export function getGazeData() {
  return { ...currentGaze };
}

/** Whether gaze data is actually being produced. */
export function isEyeTrackingAvailable() {
  return available;
}

export default { initEyeTracking, stopEyeTracking, getGazeData, isEyeTrackingAvailable };

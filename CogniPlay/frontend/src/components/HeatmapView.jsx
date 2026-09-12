import React, { useState } from 'react';

/**
 * Displays the gaze/attention heatmap returned by the AI service as a base64
 * data URI. Falls back to an explanatory placeholder when eye tracking was
 * unavailable - which is common, since it needs webcam permission.
 */
export default function HeatmapView({ heatmap, available = true }) {
  const [failed, setFailed] = useState(false);
  const usable = available && heatmap && !failed && heatmap.startsWith('data:image');

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6">
      <h3 className="font-bold text-slate-800 mb-1">Where they looked</h3>
      <p className="text-sm text-slate-500 mb-4">
        Warmer areas show where attention stayed longest during the games.
      </p>

      {usable ? (
        <figure className="m-0">
          <img
            src={heatmap}
            alt="Heatmap of the child's gaze positions across the four games. Warmer regions indicate longer fixation."
            onError={() => setFailed(true)}
            className="w-full rounded-xl border border-slate-100 bg-slate-50"
          />
          <figcaption className="text-xs text-slate-400 mt-2">
            Generated from webcam gaze sampling at 2 Hz.
          </figcaption>
        </figure>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
          <div className="text-4xl mb-3" aria-hidden="true">📷</div>
          <p className="font-semibold text-slate-600 mb-1">No eye-tracking data</p>
          <p className="text-sm text-slate-500 max-w-sm mx-auto">
            The camera wasn't available during this session. Every other result on
            this page is unaffected - the games do not require a webcam.
          </p>
        </div>
      )}
    </div>
  );
}

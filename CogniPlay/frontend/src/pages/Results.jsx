import React from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';

import RiskScoreCard from '../components/RiskScoreCard';
import ExplanationCard from '../components/ExplanationCard';
import HeatmapView from '../components/HeatmapView';
import { levelFor } from '../components/theme';

const CONDITIONS = ['dyslexia', 'dyscalculia', 'adhd'];
const CONDITION_LABEL = { dyslexia: 'Dyslexia', dyscalculia: 'Dyscalculia', adhd: 'ADHD' };

export default function Results() {
  const { state } = useLocation();
  const navigate = useNavigate();

  const response = state?.response;
  const payload = state?.payload;
  const child = state?.child || { name: 'this child' };

  // Landed here directly (refresh, bookmark) - nothing to show.
  if (!response) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 px-6 text-center">
        <div className="text-5xl mb-4">📋</div>
        <h2 className="text-xl font-bold text-slate-800 mb-2">No results to show</h2>
        <p className="text-slate-500 mb-6">Play a session first, and the report will appear here.</p>
        <Link to="/play" className="px-6 py-3 rounded-xl bg-indigo-600 text-white font-bold">
          Start a session
        </Link>
      </div>
    );
  }

  const results = response.results;

  /* The Node backend intentionally returns 200 with status 'pending' when the
     AI service is unreachable, so the child still sees a kind ending. */
  if (!results || response.status === 'pending') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 px-6 text-center">
        <div className="text-6xl mb-4">🎉</div>
        <h2 className="text-2xl font-extrabold text-slate-900 mb-2">
          {child.name} did amazing!
        </h2>
        <p className="text-slate-600 max-w-md mb-2">
          The session was saved successfully, but the analysis service could not be
          reached, so scores are not ready yet.
        </p>
        <p className="text-sm text-slate-400 max-w-md mb-8">
          Start the Python service on port 8000 and open this child from the dashboard
          to run the analysis again. No gameplay data was lost.
        </p>
        <button onClick={() => navigate('/')} className="px-6 py-3 rounded-xl bg-indigo-600 text-white font-bold">
          Back home
        </button>
      </div>
    );
  }

  // Conditions the AI could not score because the matching game had no data.
  const insufficient = results.insufficient_data || [];

  const scores = {
    dyslexia: results.dyslexia_score,
    dyscalculia: results.dyscalculia_score,
    adhd: results.adhd_score,
  };
  const levels = results.risk_levels || {};
  const flagged = CONDITIONS.filter((c) => (levels[c] || levelFor(scores[c])) !== 'Low');

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-6 py-8 text-center">
          <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
            <div className="text-5xl mb-3">🎉</div>
            <h1 className="text-2xl md:text-3xl font-extrabold text-slate-900 mb-1">
              {child.name}&apos;s Results
            </h1>
            <p className="text-slate-500">
              {payload?.session_date
                ? new Date(payload.session_date).toLocaleDateString(undefined, {
                    day: 'numeric', month: 'long', year: 'numeric',
                  })
                : 'Screening complete'}
            </p>
          </motion.div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-8">
        {/* Disclaimer sits ABOVE the scores deliberately - it must be read first. */}
        <div className="rounded-2xl bg-amber-50 border border-amber-200 p-5">
          <h2 className="font-bold text-amber-900 mb-1.5 flex items-center gap-2">
            <span aria-hidden="true">▲</span> This is a screening result, not a diagnosis
          </h2>
          <p className="text-sm text-amber-900 leading-relaxed">
            These scores describe patterns in how {child.name} played four short games.
            They cannot diagnose dyslexia, dyscalculia or ADHD, and a high score does not
            mean a child has any condition. Please treat this only as a prompt to speak
            with a teacher or a qualified specialist.
          </p>
        </div>

        {insufficient.length > 0 && (
          <div className="rounded-2xl bg-slate-100 border border-slate-300 p-5">
            <h2 className="font-bold text-slate-800 mb-1.5">
              {insufficient.length === 3 ? 'No games were completed' : 'Some areas could not be scored'}
            </h2>
            <p className="text-sm text-slate-700 leading-relaxed">
              {insufficient.map((c) => CONDITION_LABEL[c] || c).join(', ')}
              {insufficient.length === 1 ? ' was' : ' were'} not scored because the
              matching game was not finished. Those areas show as &quot;Low&quot; only
              because there is nothing to measure - that is <strong>not</strong> a
              result of &quot;no concern&quot;. Play the full session for a real score.
            </p>
          </div>
        )}

        <section>
          <h2 className="text-lg font-bold text-slate-800 mb-4">Risk indicators</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {CONDITIONS.map((c, i) => (
              <RiskScoreCard
                key={c}
                condition={c}
                score={scores[c]}
                level={levels[c]}
                delay={i * 0.1}
              />
            ))}
          </div>
        </section>

        {results.explanation && (
          <section>
            <h2 className="text-lg font-bold text-slate-800 mb-4">What drove these scores</h2>
            <div className="grid gap-4 md:grid-cols-2">
              {CONDITIONS.filter((c) => results.explanation[c]).map((c) => (
                <ExplanationCard key={c} condition={c} explanation={results.explanation[c]} />
              ))}
            </div>
          </section>
        )}

        <section className="grid gap-4 md:grid-cols-2">
          <HeatmapView heatmap={results.heatmap} available={payload?.eye_tracking?.available} />

          <div className="bg-white rounded-2xl border border-slate-200 p-6">
            <h3 className="font-bold text-slate-800 mb-1">Suggested next steps</h3>
            <p className="text-sm text-slate-500 mb-4">
              {flagged.length === 0
                ? 'Nothing was flagged in this session.'
                : `Based on ${flagged.length} area${flagged.length > 1 ? 's' : ''} worth watching.`}
            </p>
            <ul className="space-y-3">
              {(results.recommendations || []).map((r, i) => (
                <li key={i} className="flex gap-3 text-sm text-slate-700 leading-relaxed">
                  <span className="text-indigo-500 font-bold shrink-0" aria-hidden="true">→</span>
                  <span>{r}</span>
                </li>
              ))}
              {(!results.recommendations || results.recommendations.length === 0) && (
                <li className="text-sm text-slate-500">
                  Keep playing together and re-screen in a few months.
                </li>
              )}
            </ul>
          </div>
        </section>

        {results.degraded_mode && (
          <p className="text-xs text-slate-400 text-center">
            Note: the AI service ran in reduced mode (optional ML libraries not installed).
            Scores come from the built-in heuristic model.
          </p>
        )}

        <div className="flex gap-3 justify-center flex-wrap pt-4">
          <button
            onClick={() => window.print()}
            className="px-6 py-3 rounded-xl bg-white border-2 border-slate-200 font-bold text-slate-700 hover:border-slate-300"
          >
            Print report
          </button>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-3 rounded-xl bg-indigo-600 text-white font-bold hover:bg-indigo-700"
          >
            Done
          </button>
        </div>
      </main>
    </div>
  );
}

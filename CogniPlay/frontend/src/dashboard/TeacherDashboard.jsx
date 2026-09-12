import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip, Legend,
} from 'chart.js';
import { Bar } from 'react-chartjs-2';

import { CONDITION, INK, GRID, riskStyle, levelFor } from '../components/theme';
import { getAllChildren } from '../utils/api';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const CONDITIONS = ['dyslexia', 'dyscalculia', 'adhd'];

const scoreOf = (child, c) => child?.latestRiskScores?.[c]?.score ?? 0;
const levelOf = (child, c) => child?.latestRiskScores?.[c]?.level || levelFor(scoreOf(child, c));

export default function TeacherDashboard() {
  const [children, setChildren] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sortBy, setSortBy] = useState('name');

  useEffect(() => {
    getAllChildren()
      .then((list) => setChildren(list || []))
      .catch(() => setError('Could not load your class. Is the backend running on port 3001?'))
      .finally(() => setLoading(false));
  }, []);

  const sorted = useMemo(() => {
    const copy = [...children];
    if (sortBy === 'name') return copy.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
    return copy.sort((a, b) => scoreOf(b, sortBy) - scoreOf(a, sortBy));
  }, [children, sortBy]);

  const flaggedCount = useMemo(
    () => children.filter((c) => CONDITIONS.some((k) => levelOf(c, k) !== 'Low')).length,
    [children]
  );

  /* Grouped bars: one group per child, three bars per group. All three measures
     are 0-100% risk scores, so they legitimately share a single axis. */
  const chartData = {
    labels: sorted.map((c) => c.name),
    datasets: CONDITIONS.map((k) => ({
      label: CONDITION[k].label,
      data: sorted.map((c) => Math.round(scoreOf(c, k) * 100)),
      backgroundColor: CONDITION[k].color,
      borderRadius: 4,
      // 2px of surface between adjacent bars keeps the groups legible.
      borderColor: '#ffffff',
      borderWidth: { top: 0, right: 1, bottom: 0, left: 1 },
      maxBarThickness: 22,
    })),
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8, color: INK.secondary } },
      tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}%` } },
    },
    scales: {
      y: {
        min: 0, max: 100,
        ticks: { callback: (v) => `${v}%`, color: INK.muted },
        grid: { color: GRID },
        title: { display: true, text: 'Risk score', color: INK.secondary },
      },
      x: { ticks: { color: INK.muted }, grid: { display: false } },
    },
  };

  if (loading) {
    return <div className="min-h-screen grid place-items-center text-slate-400">Loading class...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-extrabold text-slate-900 mb-1">My Class</h1>
        <p className="text-slate-500 mb-6">Latest screening result for each child.</p>

        {error && (
          <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-sm text-red-700 mb-6">{error}</div>
        )}

        {children.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-10 text-center">
            <div className="text-5xl mb-3">🍎</div>
            <h2 className="font-bold text-slate-800 mb-2">No children yet</h2>
            <p className="text-slate-500 mb-6">Run a session and results will appear here.</p>
            <Link to="/play" className="px-6 py-3 rounded-xl bg-indigo-600 text-white font-bold inline-block">
              Start a session
            </Link>
          </div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3 mb-8">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <p className="text-sm text-slate-500 mb-1">Children screened</p>
                <p className="text-3xl font-extrabold tabular-nums text-slate-900">{children.length}</p>
              </div>
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <p className="text-sm text-slate-500 mb-1">Flagged for follow-up</p>
                <p className="text-3xl font-extrabold tabular-nums text-slate-900">{flaggedCount}</p>
              </div>
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <p className="text-sm text-slate-500 mb-1">No concerns</p>
                <p className="text-3xl font-extrabold tabular-nums text-slate-900">
                  {children.length - flaggedCount}
                </p>
              </div>
            </div>

            <section className="bg-white rounded-2xl border border-slate-200 p-6 mb-8">
              <div className="flex items-center justify-between mb-5 gap-4 flex-wrap">
                <div>
                  <h2 className="font-bold text-slate-800">Risk scores by child</h2>
                  <p className="text-sm text-slate-500">Lower is better.</p>
                </div>
                <label className="text-sm text-slate-600 flex items-center gap-2">
                  Sort by
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}
                    className="px-3 py-1.5 rounded-lg border border-slate-300 font-semibold"
                  >
                    <option value="name">Name</option>
                    {CONDITIONS.map((c) => (
                      <option key={c} value={c}>{CONDITION[c].label} score</option>
                    ))}
                  </select>
                </label>
              </div>

              <div style={{ height: Math.max(260, sorted.length * 46) }}>
                <Bar data={chartData} options={chartOptions} />
              </div>
            </section>

            <section className="bg-white rounded-2xl border border-slate-200 p-6">
              <h2 className="font-bold text-slate-800 mb-4">Class table</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-500 border-b border-slate-200">
                      <th className="py-2 pr-4 font-semibold">Child</th>
                      <th className="py-2 pr-4 font-semibold">Age</th>
                      {CONDITIONS.map((c) => (
                        <th key={c} className="py-2 pr-4 font-semibold">{CONDITION[c].label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((child) => (
                      <tr key={child._id} className="border-b border-slate-100">
                        <td className="py-3 pr-4 font-semibold text-slate-800">{child.name}</td>
                        <td className="py-3 pr-4 text-slate-600 tabular-nums">{child.age}</td>
                        {CONDITIONS.map((c) => {
                          const lvl = levelOf(child, c);
                          const st = riskStyle(lvl);
                          return (
                            <td key={c} className="py-3 pr-4">
                              <span className="flex items-center gap-2">
                                <span className="tabular-nums text-slate-700 w-10">
                                  {Math.round(scoreOf(child, c) * 100)}%
                                </span>
                                {/* Icon + word, so the level never relies on colour. */}
                                <span
                                  className="px-2 py-0.5 rounded-full text-xs font-bold flex items-center gap-1"
                                  style={{ backgroundColor: st.bg, color: st.color }}
                                >
                                  <span aria-hidden="true">{st.icon}</span>
                                  {lvl}
                                </span>
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <div className="rounded-2xl bg-amber-50 border border-amber-200 p-5 mt-8">
              <h3 className="font-bold text-amber-900 mb-1.5 flex items-center gap-2">
                <span aria-hidden="true">▲</span> Please handle these results carefully
              </h3>
              <p className="text-sm text-amber-900 leading-relaxed">
                These are screening indicators from a ten-minute game, not diagnoses.
                Do not group, label, or stream children based on this table. Use it only
                to decide which conversations to have with parents and specialists.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

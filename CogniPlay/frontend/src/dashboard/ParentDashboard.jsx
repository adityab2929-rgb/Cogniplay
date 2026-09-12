import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  Tooltip, Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

import RiskScoreCard from '../components/RiskScoreCard';
import { CONDITION, INK, GRID, levelFor } from '../components/theme';
import { getAllChildren, getReport } from '../utils/api';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

const CONDITIONS = ['dyslexia', 'dyscalculia', 'adhd'];

export default function ParentDashboard() {
  const [children, setChildren] = useState([]);
  const [selected, setSelected] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getAllChildren()
      .then((list) => {
        setChildren(list || []);
        if (list?.length) setSelected(list[0]);
      })
      .catch(() => setError('Could not load children. Is the backend running on port 3001?'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selected?._id) return;
    getReport(selected._id).then(setReport).catch(() => setReport(null));
  }, [selected]);

  const history = selected?.sessionHistory || [];

  /* Score trend across sessions. All three series share one 0-100% scale, so a
     single axis is correct - never a second y-axis. */
  const chartData = {
    labels: history.map((_, i) => `Session ${i + 1}`),
    datasets: CONDITIONS.map((c) => ({
      label: CONDITION[c].label,
      data: history.map((s) => Math.round(((s?.aiResults?.[`${c}_score`]) ?? 0) * 100)),
      borderColor: CONDITION[c].color,
      backgroundColor: CONDITION[c].color,
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.3,
    })),
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
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
    return <div className="min-h-screen grid place-items-center text-slate-400">Loading...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-5xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-extrabold text-slate-900 mb-1">My Child</h1>
        <p className="text-slate-500 mb-6">Screening history and latest results.</p>

        {error && (
          <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-sm text-red-700 mb-6">{error}</div>
        )}

        {children.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-10 text-center">
            <div className="text-5xl mb-3">👶</div>
            <h2 className="font-bold text-slate-800 mb-2">No child added yet</h2>
            <p className="text-slate-500 mb-6">Run a session and the results will appear here.</p>
            <Link to="/play" className="px-6 py-3 rounded-xl bg-indigo-600 text-white font-bold inline-block">
              Start a session
            </Link>
          </div>
        ) : (
          <>
            {children.length > 1 && (
              <div className="flex gap-2 mb-6 flex-wrap">
                {children.map((c) => (
                  <button
                    key={c._id}
                    onClick={() => setSelected(c)}
                    className={`px-4 py-2 rounded-xl font-semibold text-sm border-2 transition-colors ${
                      selected?._id === c._id
                        ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                        : 'border-slate-200 bg-white text-slate-600'
                    }`}
                  >
                    {c.name}
                  </button>
                ))}
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-3 mb-8">
              {CONDITIONS.map((c, i) => {
                const s = selected?.latestRiskScores?.[c];
                return (
                  <RiskScoreCard
                    key={c}
                    condition={c}
                    score={s?.score ?? 0}
                    level={s?.level || levelFor(s?.score)}
                    delay={i * 0.08}
                  />
                );
              })}
            </div>

            {history.length > 1 && (
              <section className="bg-white rounded-2xl border border-slate-200 p-6 mb-8">
                <h2 className="font-bold text-slate-800 mb-1">Scores over time</h2>
                <p className="text-sm text-slate-500 mb-5">
                  Lower is better. A falling line means the pattern is easing.
                </p>
                <div className="h-64">
                  <Line data={chartData} options={chartOptions} />
                </div>

                {/* Table view - identity never depends on colour alone. */}
                <details className="mt-4">
                  <summary className="text-sm font-semibold text-slate-600 cursor-pointer">
                    View as table
                  </summary>
                  <div className="overflow-x-auto mt-3">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-slate-500 border-b border-slate-200">
                          <th className="py-2 pr-4 font-semibold">Session</th>
                          {CONDITIONS.map((c) => (
                            <th key={c} className="py-2 pr-4 font-semibold">{CONDITION[c].label}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {history.map((s, i) => (
                          <tr key={s._id || i} className="border-b border-slate-100">
                            <td className="py-2 pr-4 text-slate-700">Session {i + 1}</td>
                            {CONDITIONS.map((c) => (
                              <td key={c} className="py-2 pr-4 tabular-nums text-slate-700">
                                {Math.round(((s?.aiResults?.[`${c}_score`]) ?? 0) * 100)}%
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </section>
            )}

            {report?.explanation && (
              <p className="text-sm text-slate-500 mb-6">{report.explanation?.dyslexia?.summary}</p>
            )}

            <div className="rounded-2xl bg-amber-50 border border-amber-200 p-5">
              <h3 className="font-bold text-amber-900 mb-1.5 flex items-center gap-2">
                <span aria-hidden="true">▲</span> A reminder
              </h3>
              <p className="text-sm text-amber-900 leading-relaxed">
                CogniPlay screens for patterns; it does not diagnose. Please discuss any
                flagged area with your child&apos;s teacher or a qualified specialist.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

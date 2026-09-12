/**
 * Shared visual tokens for every chart and score display.
 *
 * Condition hues come from the first three categorical slots, which are the
 * ones validated for colour-vision-deficiency separation across ALL pairs
 * (not just adjacent ones) - which is what a scatter/multi-series view needs.
 *
 * Risk levels use a RESERVED status palette, never the categorical hues, and
 * every risk display pairs the colour with an icon and a text label so the
 * meaning never depends on colour alone.
 */

export const CONDITION = {
  dyslexia: { label: 'Dyslexia', color: '#2a78d6', dark: '#3987e5' },
  dyscalculia: { label: 'Dyscalculia', color: '#eb6834', dark: '#d95926' },
  adhd: { label: 'ADHD', color: '#1baf7a', dark: '#199e70' },
};

export const RISK = {
  Low: { color: '#008300', bg: '#E8F5E9', icon: '✓', blurb: 'No concerns flagged' },
  Moderate: { color: '#B45309', bg: '#FEF3C7', icon: '!', blurb: 'Worth watching' },
  High: { color: '#B91C1C', bg: '#FEE2E2', icon: '▲', blurb: 'Suggest a specialist' },
};

export const INK = { primary: '#0b0b0b', secondary: '#52514e', muted: '#8a8985' };
export const GRID = '#E7E5E4';

/** Map a 0-1 score to its level. Mirrors the thresholds used server-side. */
export function levelFor(score) {
  if (score == null || Number.isNaN(score)) return 'Low';
  if (score < 0.34) return 'Low';
  if (score < 0.67) return 'Moderate';
  return 'High';
}

export const riskStyle = (level) => RISK[level] || RISK.Low;

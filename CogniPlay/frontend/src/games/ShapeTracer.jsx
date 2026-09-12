import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { logGameEvent } from '../utils/firebase';
import { initEyeTracking, stopEyeTracking, getGazeData } from '../utils/eyeTracking';

const GAME_KEY = 'shape_tracer';
const SHAPES = ['circle', 'square', 'triangle'];
const SHAPE_TIME_LIMIT_MS = 30000;
const CANVAS_SIZE = 360;
const MAX_DIST = 100;
const LOG_THROTTLE = 3;

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function getTargetPath(shapeName) {
  const cx = CANVAS_SIZE / 2;
  const cy = CANVAS_SIZE / 2;
  const points = [];

  if (shapeName === 'circle') {
    const r = 120;
    for (let i = 0; i <= 100; i++) {
      const angle = (i / 100) * Math.PI * 2;
      points.push({ x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) });
    }
  } else if (shapeName === 'square') {
    const half = 110;
    const corners = [
      { x: cx - half, y: cy - half },
      { x: cx + half, y: cy - half },
      { x: cx + half, y: cy + half },
      { x: cx - half, y: cy + half },
      { x: cx - half, y: cy - half },
    ];
    for (let i = 0; i < corners.length - 1; i++) {
      const a = corners[i];
      const b = corners[i + 1];
      for (let t = 0; t <= 24; t++) {
        const f = t / 24;
        points.push({ x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f });
      }
    }
  } else {
    // triangle
    const r = 130;
    const corners = [0, 1, 2, 0].map((i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 3;
      return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
    });
    for (let i = 0; i < corners.length - 1; i++) {
      const a = corners[i];
      const b = corners[i + 1];
      for (let t = 0; t <= 32; t++) {
        const f = t / 32;
        points.push({ x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f });
      }
    }
  }
  return points;
}

function sampleEvenly(path, count) {
  if (path.length === 0) return [];
  const result = [];
  for (let i = 0; i < count; i++) {
    const idx = Math.min(path.length - 1, Math.round((i / (count - 1)) * (path.length - 1)));
    result.push(path[idx]);
  }
  return result;
}

function computeAccuracy(targetPath, drawnPath) {
  if (drawnPath.length === 0) return 0;
  const samples = sampleEvenly(targetPath, 20);
  let totalDist = 0;
  samples.forEach((sp) => {
    let minDist = Infinity;
    drawnPath.forEach((dp) => {
      const d = Math.hypot(sp.x - dp.x, sp.y - dp.y);
      if (d < minDist) minDist = d;
    });
    totalDist += minDist;
  });
  const avgDist = totalDist / samples.length;
  return clamp(1 - avgDist / MAX_DIST, 0, 1);
}

function computeTremorScore(drawnPath) {
  if (drawnPath.length < 3) return 0;
  const angles = [];
  for (let i = 1; i < drawnPath.length; i++) {
    const dx = drawnPath[i].x - drawnPath[i - 1].x;
    const dy = drawnPath[i].y - drawnPath[i - 1].y;
    if (dx === 0 && dy === 0) continue;
    angles.push(Math.atan2(dy, dx));
  }
  if (angles.length < 2) return 0;
  const diffs = [];
  for (let i = 1; i < angles.length; i++) {
    let d = angles[i] - angles[i - 1];
    while (d > Math.PI) d -= 2 * Math.PI;
    while (d < -Math.PI) d += 2 * Math.PI;
    diffs.push(Math.abs(d));
  }
  if (diffs.length === 0) return 0;
  const mean = diffs.reduce((a, b) => a + b, 0) / diffs.length;
  const variance = diffs.reduce((a, b) => a + (b - mean) * (b - mean), 0) / diffs.length;
  const std = Math.sqrt(variance);
  return clamp(std / Math.PI, 0, 1);
}

function computePathLength(drawnPath) {
  let len = 0;
  for (let i = 1; i < drawnPath.length; i++) {
    len += Math.hypot(drawnPath[i].x - drawnPath[i - 1].x, drawnPath[i].y - drawnPath[i - 1].y);
  }
  return len;
}

export default function ShapeTracer({ childId, onComplete }) {
  const [shapeIndex, setShapeIndex] = useState(0);
  const [isDrawing, setIsDrawing] = useState(false);
  const [showResult, setShowResult] = useState(false);
  const [stars, setStars] = useState(0);
  const [finished, setFinished] = useState(false);
  const [timeLeft, setTimeLeft] = useState(SHAPE_TIME_LIMIT_MS / 1000);

  const canvasRef = useRef(null);
  const drawnPathRef = useRef([]);
  const pointCounterRef = useRef(0);
  const shapeStartRef = useRef(Date.now());
  const shapeTimeoutRef = useRef(null);
  const countdownRef = useRef(null);
  const shapeFinishedRef = useRef(false);
  const finishedRef = useRef(false);

  const resultsRef = useRef([]);

  const shapeName = SHAPES[shapeIndex];

  useEffect(() => {
    (async () => {
      try {
        await initEyeTracking(childId, GAME_KEY);
      } catch (e) {
        // swallow
      }
    })();
    return () => {
      try {
        stopEyeTracking();
      } catch (e) {
        // swallow
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clearTimers = useCallback(() => {
    if (shapeTimeoutRef.current) clearTimeout(shapeTimeoutRef.current);
    if (countdownRef.current) clearInterval(countdownRef.current);
  }, []);

  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  const drawTarget = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

    const target = getTargetPath(SHAPES[shapeIndex]);
    ctx.save();
    ctx.strokeStyle = '#bbbbbb';
    ctx.lineWidth = 3;
    ctx.setLineDash([8, 8]);
    ctx.beginPath();
    target.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.restore();

    // redraw child's current path in blue
    ctx.save();
    ctx.strokeStyle = '#2563eb';
    ctx.lineWidth = 5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.setLineDash([]);
    ctx.beginPath();
    drawnPathRef.current.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.restore();
  }, [shapeIndex]);

  const finishGame = useCallback(() => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    clearTimers();
    setFinished(true);

    const results = resultsRef.current;
    const byShape = (name) => results.find((r) => r.shape_name === name);
    const circle = byShape('circle');
    const square = byShape('square');
    const triangle = byShape('triangle');

    const circle_accuracy = circle ? circle.accuracy_score : 0;
    const square_accuracy = square ? square.accuracy_score : 0;
    const triangle_accuracy = triangle ? triangle.accuracy_score : 0;

    const overall_accuracy =
      results.length > 0
        ? results.reduce((a, r) => a + r.accuracy_score, 0) / results.length
        : 0;
    const avg_tremor_score =
      results.length > 0 ? results.reduce((a, r) => a + r.tremor_score, 0) / results.length : 0;
    const avg_drawing_speed =
      results.length > 0
        ? results.reduce((a, r) => a + r.drawing_speed_avg, 0) / results.length
        : 0;

    const payload = {
      shapes_completed: results.length,
      circle_accuracy,
      square_accuracy,
      triangle_accuracy,
      overall_accuracy,
      avg_tremor_score,
      avg_drawing_speed,
      shapes: results,
    };

    setTimeout(() => {
      if (typeof onComplete === 'function') {
        onComplete(payload);
      }
    }, 1500);
  }, [clearTimers, onComplete]);

  const finishShape = useCallback(() => {
    if (shapeFinishedRef.current) return;
    shapeFinishedRef.current = true;
    clearTimers();

    const drawnPath = drawnPathRef.current;
    const targetPath = getTargetPath(shapeName);
    const accuracy = computeAccuracy(targetPath, drawnPath);
    const tremor = computeTremorScore(drawnPath);
    const completionTimeMs = Date.now() - shapeStartRef.current;
    const pathLength = computePathLength(drawnPath);
    const drawingSpeedAvg =
      completionTimeMs > 0 ? (pathLength / completionTimeMs) * 1000 : 0;

    resultsRef.current.push({
      shape_name: shapeName,
      drawing_path: drawnPath,
      accuracy_score: accuracy,
      completion_time_ms: completionTimeMs,
      tremor_score: tremor,
      drawing_speed_avg: drawingSpeedAvg,
    });

    const starCount = Math.max(1, Math.min(5, Math.round(accuracy * 5)));
    setStars(starCount);
    setShowResult(true);
    setIsDrawing(false);

    setTimeout(() => {
      setShowResult(false);
      if (shapeIndex >= SHAPES.length - 1) {
        finishGame();
      } else {
        setShapeIndex((prev) => prev + 1);
      }
    }, 2000);
  }, [shapeName, shapeIndex, clearTimers, finishGame]);

  // Setup each shape round
  useEffect(() => {
    if (finishedRef.current) return undefined;
    shapeFinishedRef.current = false;
    drawnPathRef.current = [];
    pointCounterRef.current = 0;
    shapeStartRef.current = Date.now();
    setTimeLeft(SHAPE_TIME_LIMIT_MS / 1000);
    setIsDrawing(false);

    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
    }
    drawTarget();

    shapeTimeoutRef.current = setTimeout(() => {
      finishShape();
    }, SHAPE_TIME_LIMIT_MS);

    countdownRef.current = setInterval(() => {
      setTimeLeft((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    return () => {
      clearTimers();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shapeIndex]);

  const getCanvasCoords = useCallback((clientX, clientY) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const scaleX = CANVAS_SIZE / rect.width;
    const scaleY = CANVAS_SIZE / rect.height;
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    };
  }, []);

  const addPoint = useCallback(
    (x, y) => {
      const point = { x, y, timestamp: Date.now() };
      drawnPathRef.current.push(point);
      pointCounterRef.current += 1;
      drawTarget();

      if (pointCounterRef.current % LOG_THROTTLE === 0) {
        logGameEvent(childId, GAME_KEY, {
          type: 'drawing_point',
          x,
          y,
          pressure: 1.0,
          shape_name: shapeName,
        });
      }
    },
    [childId, shapeName, drawTarget]
  );

  const handlePointerDown = useCallback(
    (clientX, clientY) => {
      if (shapeFinishedRef.current || finishedRef.current) return;
      setIsDrawing(true);
      const { x, y } = getCanvasCoords(clientX, clientY);
      addPoint(x, y);
    },
    [getCanvasCoords, addPoint]
  );

  const handlePointerMove = useCallback(
    (clientX, clientY) => {
      if (!isDrawing || shapeFinishedRef.current || finishedRef.current) return;
      const { x, y } = getCanvasCoords(clientX, clientY);
      addPoint(x, y);
    },
    [isDrawing, getCanvasCoords, addPoint]
  );

  const handlePointerUp = useCallback(() => {
    if (!isDrawing) return;
    setIsDrawing(false);
    if (drawnPathRef.current.length > 2) {
      finishShape();
    }
  }, [isDrawing, finishShape]);

  // Mouse handlers
  const onMouseDown = (e) => handlePointerDown(e.clientX, e.clientY);
  const onMouseMove = (e) => handlePointerMove(e.clientX, e.clientY);
  const onMouseUp = () => handlePointerUp();

  // Touch handlers
  const onTouchStart = (e) => {
    e.preventDefault();
    const t = e.touches[0];
    if (t) handlePointerDown(t.clientX, t.clientY);
  };
  const onTouchMove = (e) => {
    e.preventDefault();
    const t = e.touches[0];
    if (t) handlePointerMove(t.clientX, t.clientY);
  };
  const onTouchEnd = (e) => {
    e.preventDefault();
    handlePointerUp();
  };

  if (finished) {
    return (
      <div className="w-full h-full min-h-[600px] flex flex-col items-center justify-center bg-white rounded-3xl">
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', duration: 0.6 }}
          className="text-center"
        >
          <div className="text-7xl mb-4">Great Tracing! ✏️⭐</div>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full min-h-[600px] flex flex-col items-center justify-center bg-indigo-50 rounded-3xl p-4">
      <div className="absolute top-4 left-4 z-20 bg-white/90 rounded-2xl px-5 py-2 shadow-lg">
        <span className="text-xl font-extrabold text-indigo-700 capitalize">
          Shape {shapeIndex + 1}/{SHAPES.length}: {shapeName}
        </span>
      </div>
      <div className="absolute top-4 right-4 z-20 bg-white/90 rounded-2xl px-5 py-2 shadow-lg">
        <span className="text-xl font-extrabold text-indigo-700">{timeLeft}s</span>
      </div>

      <div className="mb-4 mt-16 bg-yellow-200 rounded-3xl px-8 py-3 shadow-xl">
        <h1 className="text-xl md:text-2xl font-extrabold text-center text-indigo-900">
          Trace the shape! ✏️
        </h1>
      </div>

      <div className="bg-white rounded-3xl shadow-2xl p-2 touch-none">
        <canvas
          ref={canvasRef}
          width={CANVAS_SIZE}
          height={CANVAS_SIZE}
          className="rounded-2xl touch-none"
          style={{ width: CANVAS_SIZE, height: CANVAS_SIZE, touchAction: 'none' }}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
        />
      </div>

      <AnimatePresence>
        {showResult && (
          <motion.div
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.5 }}
            className="absolute inset-0 z-30 flex items-center justify-center bg-white/80 rounded-3xl"
          >
            <div className="text-center">
              <div className="text-3xl font-extrabold text-indigo-800 mb-4">Nice work!</div>
              <div className="text-6xl">
                {'⭐'.repeat(stars)}
                {'☆'.repeat(5 - stars)}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

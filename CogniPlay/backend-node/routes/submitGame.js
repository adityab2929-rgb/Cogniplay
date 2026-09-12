const express = require('express');
const axios = require('axios');
const jwt = require('jsonwebtoken');
const Session = require('../models/Session');
const Child = require('../models/Child');

const router = express.Router();

// Optional auth: if a Bearer token is present and valid, attach req.user.
// This route must still work for unauthenticated shared-device play.
function optionalAuth(req, res, next) {
  try {
    const authHeader = req.headers['authorization'] || '';
    const parts = authHeader.split(' ');

    if (parts.length === 2 && parts[0] === 'Bearer' && parts[1]) {
      try {
        const decoded = jwt.verify(parts[1], process.env.JWT_SECRET);
        req.user = { id: decoded.id, role: decoded.role };
      } catch (err) {
        // Ignore invalid/expired token - route is still accessible without auth.
      }
    }
  } catch (err) {
    // Never throw from auth parsing.
  }
  next();
}

router.use(optionalAuth);

router.post('/', async (req, res) => {
  try {
    const payload = req.body || {};
    const {
      child_id,
      letter_land,
      number_ninja,
      butterfly_game,
      shape_tracer,
      eye_tracking
    } = payload;

    if (!child_id) {
      return res.status(400).json({ error: 'child_id is required' });
    }

    if (!letter_land || !number_ninja || !butterfly_game || !shape_tracer) {
      return res.status(400).json({
        error: 'letter_land, number_ninja, butterfly_game and shape_tracer are all required'
      });
    }

    const session = new Session({
      childId: child_id,
      gameData: {
        letterLand: letter_land,
        numberNinja: number_ninja,
        butterflyGame: butterfly_game,
        shapeTracer: shape_tracer,
        eyeTracking: eye_tracking || []
      },
      status: 'processing'
    });

    await session.save();

    const pythonAiUrl = process.env.PYTHON_AI_URL || 'http://localhost:8000';

    try {
      const response = await axios.post(
        `${pythonAiUrl}/predict-learning-pattern`,
        payload,
        { timeout: 120000 }
      );

      const results = response.data;

      session.aiResults = {
        dyslexia_score: results.dyslexia_score,
        dyscalculia_score: results.dyscalculia_score,
        adhd_score: results.adhd_score,
        risk_levels: results.risk_levels,
        explanation: results.explanation,
        heatmap: results.heatmap
      };
      session.status = 'completed';
      session.analysedAt = new Date();

      await session.save();

      const child = await Child.findById(child_id);
      if (child) {
        const riskLevels = results.risk_levels || {};

        child.latestRiskScores = {
          dyslexia: {
            score: results.dyslexia_score,
            level: riskLevels.dyslexia
          },
          dyscalculia: {
            score: results.dyscalculia_score,
            level: riskLevels.dyscalculia
          },
          adhd: {
            score: results.adhd_score,
            level: riskLevels.adhd
          }
        };
        child.sessionHistory.push(session._id);
        await child.save();
      }

      return res.status(200).json({
        sessionId: session._id,
        status: 'completed',
        results: session.aiResults
      });
    } catch (aiError) {
      console.error('AI analysis failed for session', session._id.toString(), ':', aiError.message);

      session.status = 'pending';
      await session.save();

      return res.status(200).json({
        sessionId: session._id,
        status: 'pending',
        results: null,
        message: 'AI analysis is queued and will be available shortly.'
      });
    }
  } catch (err) {
    console.error('Submit game error:', err);
    return res.status(500).json({ error: 'Something went wrong while submitting game session' });
  }
});

module.exports = router;

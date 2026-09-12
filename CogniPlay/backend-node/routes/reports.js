const express = require('express');
const Session = require('../models/Session');
const Child = require('../models/Child');
const authMiddleware = require('../middleware/authMiddleware');

const router = express.Router();

router.use(authMiddleware);

// GET /:childId
router.get('/:childId', async (req, res) => {
  try {
    const child = await Child.findById(req.params.childId);

    if (!child) {
      return res.status(404).json({ error: 'Child not found' });
    }

    const session = await Session.findOne({
      childId: req.params.childId,
      status: 'completed'
    }).sort({ createdAt: -1 });

    if (!session) {
      return res.status(404).json({ error: 'No completed session found for this child' });
    }

    return res.status(200).json({
      child: {
        name: child.name,
        age: child.age
      },
      riskScores: {
        dyslexia: session.aiResults ? session.aiResults.dyslexia_score : undefined,
        dyscalculia: session.aiResults ? session.aiResults.dyscalculia_score : undefined,
        adhd: session.aiResults ? session.aiResults.adhd_score : undefined,
        risk_levels: session.aiResults ? session.aiResults.risk_levels : undefined
      },
      explanation: session.aiResults ? session.aiResults.explanation : undefined,
      heatmap: session.aiResults ? session.aiResults.heatmap : undefined,
      sessionDate: session.createdAt
    });
  } catch (err) {
    console.error('Get report error:', err);
    return res.status(500).json({ error: 'Something went wrong while fetching report' });
  }
});

module.exports = router;

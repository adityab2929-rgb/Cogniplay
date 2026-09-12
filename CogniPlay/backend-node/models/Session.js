const mongoose = require('mongoose');

const sessionSchema = new mongoose.Schema({
  childId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Child',
    required: true
  },
  gameData: {
    letterLand: { type: Object },
    numberNinja: { type: Object },
    butterflyGame: { type: Object },
    shapeTracer: { type: Object },
    eyeTracking: { type: Array }
  },
  aiResults: {
    dyslexia_score: Number,
    dyscalculia_score: Number,
    adhd_score: Number,
    risk_levels: { type: Object },
    explanation: { type: Object },
    heatmap: String
  },
  status: {
    type: String,
    enum: ['pending', 'processing', 'completed'],
    default: 'pending'
  },
  pdfReportUrl: {
    type: String
  },
  createdAt: {
    type: Date,
    default: Date.now
  },
  analysedAt: {
    type: Date
  }
});

module.exports = mongoose.model('Session', sessionSchema);

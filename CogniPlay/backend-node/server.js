require('dotenv').config();

const express = require('express');
const cors = require('cors');
const mongoose = require('mongoose');

const authRoutes = require('./routes/auth');
const submitGameRoutes = require('./routes/submitGame');
const childrenRoutes = require('./routes/children');
const reportsRoutes = require('./routes/reports');
const authMiddleware = require('./middleware/authMiddleware');

const app = express();

app.use(express.json({ limit: '10mb' }));

app.use(
  cors({
    origin: process.env.CORS_ORIGIN || 'http://localhost:3000',
    credentials: true
  })
);

app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok' });
});

app.use('/api/auth', authRoutes);
app.use('/api/submit-game', submitGameRoutes);
app.use('/api/child', childrenRoutes);
app.get('/api/children/all', authMiddleware, childrenRoutes.getAllChildren);
app.use('/api/report', reportsRoutes);

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

// Error-handling middleware
app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(err.status || 500).json({ error: err.message || 'Internal server error' });
});

const PORT = process.env.PORT || 3001;
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/cogniplay';

mongoose
  .connect(MONGODB_URI)
  .then(() => {
    console.log('MongoDB connected successfully');
  })
  .catch((err) => {
    console.warn('WARNING: MongoDB connection failed. Server will still start, but database features will not work.');
    console.warn('MongoDB error:', err.message);
  });

app.listen(PORT, () => {
  console.log(`CogniPlay backend running at http://localhost:${PORT}`);
});

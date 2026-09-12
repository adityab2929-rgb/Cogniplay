const express = require('express');
const Child = require('../models/Child');
const authMiddleware = require('../middleware/authMiddleware');

const router = express.Router();

router.use(authMiddleware);

// POST /add
router.post('/add', async (req, res) => {
  try {
    const { name, age, gender } = req.body || {};

    if (!name || age === undefined || age === null) {
      return res.status(400).json({ error: 'name and age are required' });
    }

    const childData = { name, age, gender };

    if (req.user.role === 'parent') {
      childData.parentId = req.user.id;
    } else if (req.user.role === 'teacher') {
      childData.teacherId = req.user.id;
    }

    const child = new Child(childData);
    await child.save();

    return res.status(201).json(child);
  } catch (err) {
    console.error('Add child error:', err);
    return res.status(500).json({ error: 'Something went wrong while adding child' });
  }
});

// GET /:id
router.get('/:id', async (req, res) => {
  try {
    const child = await Child.findById(req.params.id).populate({
      path: 'sessionHistory',
      options: { sort: { createdAt: -1 }, limit: 10 }
    });

    if (!child) {
      return res.status(404).json({ error: 'Child not found' });
    }

    const belongsToUser =
      (child.parentId && child.parentId.toString() === req.user.id) ||
      (child.teacherId && child.teacherId.toString() === req.user.id);

    if (!belongsToUser) {
      return res.status(403).json({ error: 'You do not have access to this child' });
    }

    return res.status(200).json(child);
  } catch (err) {
    console.error('Get child error:', err);
    return res.status(500).json({ error: 'Something went wrong while fetching child' });
  }
});

// Handler for GET /all, mounted separately at /api/children/all
async function getAllChildren(req, res) {
  try {
    const filter = {};

    if (req.user.role === 'teacher') {
      filter.teacherId = req.user.id;
    } else if (req.user.role === 'parent') {
      filter.parentId = req.user.id;
    }

    const children = await Child.find(filter);

    return res.status(200).json(children);
  } catch (err) {
    console.error('Get all children error:', err);
    return res.status(500).json({ error: 'Something went wrong while fetching children' });
  }
}

router.get('/all', getAllChildren);

module.exports = router;
module.exports.getAllChildren = getAllChildren;
module.exports.router = router;

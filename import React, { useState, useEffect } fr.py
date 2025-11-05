import React, { useState, useEffect } from 'react';
import { Container, Typography, Grid, Card, CardContent, Checkbox, Button, TextField, Select, MenuItem } from '@mui/material';
import { Add } from '@mui/icons-material';

// Sample tasks from synopsis
const initialTasks = [
  { id: 1, title: 'Backend Setup & API Development', description: 'Set up FastAPI server, design DB schema.', dueDate: 'Week 1', priority: 'High', category: 'Week 1', status: false, assignedTo: 'Varun Reniwal' },
  // Add more tasks here...
];

function App() {
  const [tasks, setTasks] = useState(initialTasks);
  const [filter, setFilter] = useState('All');

  const handleToggle = (id) => {
    setTasks(tasks.map(task => task.id === id ? { ...task, status: !task.status } : task));
  };

  const filteredTasks = filter === 'All' ? tasks : tasks.filter(task => task.category === filter);

  return (
    <Container maxWidth="lg" style={{ backgroundColor: '#F5F5F5', padding: '20px' }}>
      <Typography variant="h4" gutterBottom style={{ color: '#333', fontWeight: 'bold' }}>Smart Canteen Project To-Do</Typography>
      <Button variant="contained" color="primary" startIcon={<Add />}>Add Task</Button>
      <Select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ marginLeft: '20px' }}>
        <MenuItem value="All">All</MenuItem>
        <MenuItem value="Week 1">Week 1</MenuItem>
        {/* Add more weeks */}
      </Select>
      <Grid container spacing={2} style={{ marginTop: '20px' }}>
        {filteredTasks.map(task => (
          <Grid item xs={12} sm={6} md={4} key={task.id}>
            <Card style={{ borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
              <CardContent>
                <Typography variant="h6">{task.title}</Typography>
                <Typography variant="body2" color="textSecondary">{task.description}</Typography>
                <Typography variant="caption">Due: {task.dueDate} | Assigned: {task.assignedTo}</Typography>
                <Checkbox checked={task.status} onChange={() => handleToggle(task.id)} />
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Container>
  );
}

export default App;

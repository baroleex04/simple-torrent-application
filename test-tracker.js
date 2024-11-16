// tracker.js
const express = require('express');
const app = express();
const PORT = 4000;
const TRACKER_URL = 'http://192.168.68.52';
let peers = []; // List to hold connected peers

// Endpoint for a peer to register with the tracker
app.post('/register', (req, res) => {
    const { ip, port } = req.query;
    const peer = `${ip}:${port}`;
    if (!peers.includes(peer)) {
        peers.push(peer);
    }
    res.send({ message: 'Registered', peers });
});

// Endpoint to fetch the list of peers
app.get('/peers', (req, res) => {
    res.send(peers);
});

app.listen(PORT, () => {
    console.log(`Tracker running on ${TRACKER_URL}:${PORT}`);
});

// peer.js
const express = require('express');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const app = express();

const PEER_PORT = process.env.PEER_PORT || 4000;
const TRACKER_URL = 'http://localhost:3000';
let connectedPeers = [];

// Register the peer with the tracker
async function registerWithTracker() {
    const ip = '127.0.0.1'; // Replace with your machine's IP for cross-machine connection
    try {
        const response = await axios.post(`${TRACKER_URL}/register`, null, {
            params: { ip, port: PEER_PORT }
        });
        connectedPeers = response.data.peers.filter(peer => peer !== `${ip}:${PEER_PORT}`);
        console.log('Connected peers:', connectedPeers);
    } catch (error) {
        console.error('Error registering with tracker:', error.message);
    }
}

// Share a file with other peers
app.get('/file/:filename', (req, res) => {
    const filePath = path.join(__dirname, 'shared', req.params.filename);
    if (fs.existsSync(filePath)) {
        res.download(filePath);
    } else {
        res.status(404).send('File not found');
    }
});

// Request a file from a peer
async function requestFile(peer, filename) {
    try {
        const response = await axios.get(`http://${peer}/file/${filename}`, {
            responseType: 'stream'
        });
        const filePath = path.join(__dirname, 'downloads', filename);
        response.data.pipe(fs.createWriteStream(filePath));
        console.log(`Downloaded ${filename} from ${peer}`);
    } catch (error) {
        console.error('Error requesting file:', error.message);
    }
}

app.listen(PEER_PORT, () => {
    console.log(`Peer running on http://localhost:${PEER_PORT}`);
    registerWithTracker();
});

// Simulate requesting a file from the first connected peer
setTimeout(() => {
    if (connectedPeers.length > 0) {
        const peer = connectedPeers[0];
        requestFile(peer, 'example.txt'); // Replace 'example.txt' with your file name
    }
}, 10000);

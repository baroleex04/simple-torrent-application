// signaling-server.js
const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 3000 });
const peers = new Set();

wss.on('connection', (ws) => {
    peers.add(ws);
    console.log('New peer connected');

    ws.on('message', (message) => {
        // Broadcast the message to all other peers
        peers.forEach((peer) => {
            if (peer !== ws && peer.readyState === WebSocket.OPEN) {
                peer.send(message);
            }
        });
    });

    ws.on('close', () => {
        peers.delete(ws);
        console.log('Peer disconnected');
    });
});

console.log('Signaling server running on ws://localhost:3000');

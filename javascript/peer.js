// peer.js
const net = require("net");
const fs = require("fs");
const peerId = process.argv[2];
const trackerHost = "127.0.0.1";
const trackerPort = 4000;
// const pieces = ["piece1", "piece2"]; // Example pieces this peer has

// Connect to tracker
const trackerClient = net.createConnection(trackerPort, trackerHost, () => {
    console.log("Connected to tracker");
    const filePath = `data/peer${peerId}`;
    const fileList = fs.readdirSync(filePath)
    trackerClient.write(JSON.stringify({
        type: "register",
        peerId: peerId,
        port: 4000 + Math.floor(Math.random() * 1000),
        pieces: fileList,
    }));
});

trackerClient.on("data", (data) => {
    const message = JSON.parse(data.toString());
    if (message.type === "registered") {
        console.log(`Registered with tracker as ${message.peerId}`);
    } else {
        const peers = JSON.parse(data);
        let otherPeers = [];
        for (let peer of peers) {
            if (peer.peerId != peerId) {
                otherPeers.push(peer);
            }
        }
        console.log("Other peers received:", otherPeers);
    }
});

// Sample file piece request to another peer
const requestPiece = (peer) => {
    const client = net.createConnection(peer.port, peer.ip, () => {
        console.log(`Connected to peer ${peer.ip}:${peer.port}`);
        client.write("pieceRequest,piece1"); // Example of requesting "piece1"
    });

    client.on("data", (data) => {
        console.log(`Received piece from peer: ${data.toString()}`);
        fs.writeFileSync("downloaded_piece1", data); // Save piece
        client.end();
    });
};

// Periodically ask tracker for peers
setInterval(() => {
    trackerClient.write(JSON.stringify({ type: "getPeers" }));
}, 5000);

// test request file from peer 1 to peer 2
const fs = require("fs");
const net = require("net");
const data = fs.readFileSync("peerList.json");
const peers = JSON.parse(data);
const peerId = process.argv[2];
const peerIdDest = process.argv[3];
const fileRequest = process.argv[4];
const peer = peers.find(p => p.peerId == peerIdDest);

if (!peerId || !peerIdDest || !fileRequest) {
    console.error("Usage: node script.js <peerId> <peerIdDest> <fileRequest>");
    process.exit(1);
}

const peerClient = net.createConnection(peer.port, peer.ip, () => {
    console.log(`Connected to Peer ${peer.peerId} at ${peer.ip}:${peer.port}`);
    
    // Send the request for the file
    peerClient.write(`pieceRequest,${fileRequest}`);
});

peerClient.on("data", (data) => {
    console.log(`Received data from Peer ${peer.peerId}`);
    
    // Save the file received from Peer 2
    fs.writeFileSync(`data/peer${peerId}/downloaded_${fileRequest}`, data);
    
    // Log success message
    console.log(`Successfully downloaded ${fileRequest} from Peer ${peer.peerId}`);

    // Close the connection
    peerClient.end();
});

peerClient.on("end", () => {
    console.log(`Disconnected from Peer ${peer.peerId}`);
});

peerClient.on("error", (err) => {
    console.error("Connection error:", err.message);
});
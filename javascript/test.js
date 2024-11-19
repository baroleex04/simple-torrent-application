const fs = require("fs");
const peerId = process.argv[2];
const data = fs.readFileSync("peerList.json");
const peers = JSON.parse(data);
const peer = peers.find(p => p.peerId == peerId);
const port = peer.port || 4001;

console.log(port);
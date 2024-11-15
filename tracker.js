// tracker.js
const net = require("net");
const fs = require("fs");
const port = 4000;
const peerListFile = "peerList.json";
let peers = {};

if (fs.existsSync(peerListFile)) {
    peers = JSON.parse(fs.readFileSync(peerListFile));
}

const savePeers = () => {
    fs.writeFileSync(peerListFile, JSON.stringify(peers, null, 2));
};

const tracker = net.createServer((socket) => {
    let currentPeer = null;

    socket.on("data", (data) => {
        const message = JSON.parse(data.toString());
        
        if (message.type === "register") {
            currentPeer = {
                peerId: message.peerId,
                ip: socket.remoteAddress,
                port: message.port,
                pieces: message.pieces,
            };

            // Add peer to list if not already present
            const exists = peers.some((peer) => peer.peerId === currentPeer.peerId);
            if (!exists) {
                peers.push(currentPeer);
                console.log(`Peer registered: ${JSON.stringify(currentPeer)}`);
                savePeers();

                socket.write(
                    JSON.stringify({ type: "registered", peerId: currentPeer.peerId })
                );
            }
        } else if (message.type === "getPeers") {
            socket.write(JSON.stringify(peers));
        }
    });

    socket.on("end", () => {
        if (currentPeer) {
            console.log(`Peer disconnected: ${currentPeer.peerId}`);
            peers = peers.filter((peer) => peer.peerId !== currentPeer.peerId);
            savePeers();
        }
    });

    // socket.on("close", () => {
    //     if (currentPeer) {
    //         console.log(`Peer disconnected: ${currentPeer.peerId}`);
    //         peers = peers.filter((peer) => peer.peerId !== currentPeer.peerId);
    //         savePeers();
    //     }
    // });

    socket.on("error", (err) => {
        console.error(`Socket error: ${err.message}`);
    });
});

tracker.listen(port, () => {
    console.log(`Tracker running on port: ${port}`);
});

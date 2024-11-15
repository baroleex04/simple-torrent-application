const net = require("net");
const fs = require("fs");
const peerId = process.argv[2];
const data = fs.readFileSync("peerList.json");
const peers = JSON.parse(data);
const peer = peers.find(p => p.peerId == peerId);
const port = peer.port || 4001;

// Start a server to handle file requests
const pieceServer = net.createServer((socket) => {
    socket.on("data", (data) => {
        const message = data.toString().split(",");
        
        if (message[0] === "pieceRequest") {
            const pieceName = message[1];

            // Check if the requested piece exists
            if (fs.existsSync(pieceName)) {
                const pieceData = fs.readFileSync(`data/peer${peer.peerId}/${pieceName}`);
                socket.write(pieceData); // Send the file piece to the client
            } else {
                socket.write("Piece not available"); // Send error if file not found
            }
        }
    });

    socket.on("end", () => {
        console.log("Peer 1 disconnected");
    });

    socket.on("error", (err) => {
        console.log("Error:", err.message);
    });
});

// Start the server on Peer 2's port
pieceServer.listen(port, () => {
    console.log(`Piece server running on port ${port}`);
});

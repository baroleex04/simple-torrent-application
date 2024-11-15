// peerPieceServer.js
const net = require("net");
const fs = require("fs");

const pieceServer = net.createServer((socket) => {
    socket.on("data", (data) => {
        const message = data.toString().split(",");
        if (message[0] === "pieceRequest") {
            const pieceName = message[1];
            if (fs.existsSync(pieceName)) {
                const pieceData = fs.readFileSync(pieceName);
                socket.write(pieceData);
            } else {
                socket.write("Piece not available");
            }
        }
    });
});

pieceServer.listen(4001, () => {
    console.log("Piece server running on port 4001");
});

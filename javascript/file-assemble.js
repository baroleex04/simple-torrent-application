const fs = require("fs");

const assemblePieces = (numPieces, outputFile) => {
    const output = fs.createWriteStream(outputFile);
    for (let i = 0; i < numPieces; i++) {
        const pieceData = fs.readFileSync(`piece${i}`);
        output.write(pieceData);
    }
    output.end();
    console.log(`File assembled as ${outputFile}`);
};

assemblePieces(4, "assembled_file.txt"); // Adjust numPieces accordingly

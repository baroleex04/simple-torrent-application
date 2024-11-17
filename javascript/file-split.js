const fs = require("fs");

const splitFileIntoPieces = (filePath, pieceSize) => {
    const fileData = fs.readFileSync(filePath);
    let pieceIndex = 0;
    for (let i = 0; i < fileData.length; i += pieceSize) {
        const pieceData = fileData.slice(i, i + pieceSize);
        fs.writeFileSync(`piece${pieceIndex}`, pieceData);
        pieceIndex++;
    }
    console.log(`File split into ${pieceIndex} pieces.`);
};

splitFileIntoPieces("path/to/your/file.txt", 1024 * 1024); // Split into 1 MB pieces

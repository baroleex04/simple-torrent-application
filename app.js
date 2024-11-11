import express from "express";
import multer from "multer";
import WebTorrent from "webtorrent-hybrid";
import path from "path";
import { fileURLToPath } from 'url';

// Define __dirname in ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const client = new WebTorrent();

// Configure Multer for file uploads
const upload = multer({ dest: "uploads/" });

// Set EJS as the view engine
app.set("view engine", "ejs");
app.use(express.static("public"));

// Route for the homepage
app.get("/", (req, res) => {
    res.render("index", { torrents: client.torrents });
});

// Upload and seed a file as a torrent
app.post("/upload", upload.single("file"), (req, res) => {
    const filePath = path.join(__dirname, req.file.path);

    client.seed(filePath, (torrent) => {
        console.log("Seeding:", torrent.infoHash);

        res.render("index", {
            torrents: client.torrents,
            message: `Seeding started for ${req.file.originalname}`,
        });
    });
});

// Download a torrent
app.get("/download", (req, res) => {
    const magnetURI = req.query.magnetURI;

    if (!magnetURI) {
        return res.status(400).send("Magnet URI required.");
    }

    client.add(magnetURI, (torrent) => {
        const file = torrent.files.find((file) => file.name);

        file.getBuffer((err, buffer) => {
            if (err) {
                return res.status(500).send("Error downloading file.");
            }

            res.setHeader("Content-Disposition", `attachment; filename="${file.name}"`);
            res.send(buffer);
        });
    });
});

// Start the server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));

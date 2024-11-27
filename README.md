# A TORRENT-LIKE APPLICATION

Tutorial of running the application

- Open the terminal and point to the folder of application
- Run "node tracker.js": build the tracker
- Run "node peer.js <peerId>" on a new terminal: build the peers, which connect automatically to the tracker, in case you want to have multiple peers then open multiple terminal and on each terminal, specify a distinct value of peerId
- To process downloading file from peer to peer: first run "node peer-host.js <peer owns the file>" on a new terminal, second run "node peer-request.js <peer requests file> <peer owns file> <file name>" to download the file.


import json

data = [
    {
        "info_hash": {
            "name": "1",
            "piece length": 5,
            "pieces": [
                {"piece": "e7bbf533c5834db9a869396607a68f1aa3ad219b"},
                {"piece": "c1ee9f5a6ab4625e6cd68b19bd4e0a4d2e20128a"},
                {"piece": "9cddd2d86e9d898f2d5a4a735dfa8482d9bfe2a2"},
                {"piece": "7bad7879176075eaed52b57088a5e19497b22f81"},
                {"piece": "08e171beaa83307455d19feef66e291861c883aa"},
                {"piece": "68d0c5f63733a10adf873ea46886624af3ad0b66"},
                {"piece": "99a6ca127ea67454aac070553ef80f790820ff95"},
                {"piece": "6867f79c8af77bb2a6b3585c9cd8511e352656e3"},
                {"piece": "f493c7d30c14c602367f217498c9c22f6a3ed730"},
                {"piece": "4f98e36fdfd7cc6ce87f13da293d57e3ef5f2c34"},
                {"piece": "065edc883ca4965ae50c344e624d201022691f56"}
            ],
            "files": [
                {
                    "path": ["peer1", "test_file_1.txt"],
                    "length": 25
                },
                {
                    "path": ["peer1", "test_file_2.txt"],
                    "length": 30
                }
            ]
        },
        "peer_id": "1",
        "port": "4001",
        "uploaded": 20,
        "downloaded": 0,
        "left": 0,
        "compact": 1,
        "ip": "192.168.1.6"
    },
    {
        "info_hash": {
            "name": "3",
            "piece length": 5,
            "pieces": [
                {"piece": "e7bbf533c5834db9a869396607a68f1aa3ad219b"},
                {"piece": "c1ee9f5a6ab4625e6cd68b19bd4e0a4d2e20128a"},
                {"piece": "9cddd2d86e9d898f2d5a4a735dfa8482d9bfe2a2"},
                {"piece": "7bad7879176075eaed52b57088a5e19497b22f81"},
                {"piece": "08e171beaa83307455d19feef66e291861c883aa"}
            ],
            "files": [
                {
                    "path": ["peer3", "test_file_1.txt"],
                    "length": 25
                }
            ]
        },
        "peer_id": "3",
        "port": "4003",
        "uploaded": 20,
        "downloaded": 0,
        "left": 0,
        "compact": 1,
        "ip": "192.168.1.6"
    }
]

def find_file_info_with_peers(data, target_file):
    piece_to_peers = {}
    for peer in data:
        peer_ip = peer["ip"]
        peer_port = peer["port"]
        files = peer["info_hash"]["files"]
        
        for file in files:
            if target_file in file["path"]:
                file_length = file["length"]
                piece_length = peer["info_hash"]["piece length"]
                num_pieces = -(-file_length // piece_length)  # Ceiling division
                pieces = peer["info_hash"]["pieces"][:num_pieces]
                
                for piece in pieces:
                    piece_hash = piece["piece"]
                    if piece_hash not in piece_to_peers:
                        piece_to_peers[piece_hash] = []
                    piece_to_peers[piece_hash].append({"ip": peer_ip, "port": peer_port})
    
    return piece_to_peers

# Search for the file
file_name = "test_file_2.txt"
piece_to_peers_mapping = find_file_info_with_peers(data, file_name)

# Print the mapping
if piece_to_peers_mapping:
    print(f"Piece-to-peer mapping for '{file_name}':")
    print(json.dumps(piece_to_peers_mapping, indent=4))
else:
    print(f"No data found for file '{file_name}'.")

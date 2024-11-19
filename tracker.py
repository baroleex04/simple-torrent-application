# tracker create a server
# peer connect to tracker and tracker write down a record of peer
import socket
import threading
import json
import signal
import sys
import time

# Opening JSON file and load on tracker_data
file = open('tracker1/tracker.json')
tracker_data = json.load(file)

# Save the json file data
def save_tracker_data():
    with open('tracker1/tracker.json', 'w') as file:
        json.dump(tracker_data, file, indent=4)
        
# Function to get the list of available peers, excluding the requesting peer
def get_peers_excluding(peer_id):
    peers = []
    for peer in tracker_data:
        if peer["peer_id"] != peer_id:
            peers.append(peer)
    return peers

# Function to handle client connection
def handle_client(conn, addr):
    while True:
        try:
            data = conn.recv(4096).decode('utf-8')
            if data.startswith("REGISTER"):
                _, peer_id, info_hash = data.split('|')
                print(f"[REGISTER] Peer {peer_id} connected.")
                # Write to tracker_data the new peer
                # info_hash, peer_id, port, ip
                peer_ip = addr[0]
                peer_port = addr[1]
                info_hash_object = json.loads(info_hash)
                new_peer = {
                    "info_hash": info_hash_object,
                    "peer_id": peer_id,
                    "port": peer_port,
                    "uploaded": 20, # default number of upload bytes
                    "downloaded": 0, # default number of download bytes
                    "left": 0, # default number of left bytes
                    "compact": 1, # default number of status
                    "ip": peer_ip
                }
                if not any(obj["peer_id"] == peer_id for obj in tracker_data):
                    tracker_data.append(new_peer)  # Append new object
                    save_tracker_data()
                    conn.sendall(b"REGISTERED")
                else:
                    print(f"peer_id {peer_id} already exists in the list.")
                    conn.sendall(b"EXISTED PEER ID, CAN NOT REGISTERED")
            elif data.startswith("DISCONNECT"):
                _, peer_id = data.split('|')
                print(f"[INFO] Peer {peer_id} requested to disconnect.")
                # Check if the peer exists in the tracker_data
                peer_to_remove = next((obj for obj in tracker_data if obj["peer_id"] == peer_id), None)
    
                if peer_to_remove is None:
                    print(f"peer_id {peer_id} did not exist in the list.")
                    conn.sendall(b"PEER ID DID NOT EXIST, CAN NOT DISCONNECT")
                else:
                    # Peer is found, remove it from the list
                    tracker_data.remove(peer_to_remove)
                    save_tracker_data()
                    conn.sendall(b"DISCONNECTED SUCCESSFULLY")
                    print(f"Peer {peer_id} successfully disconnected.")
                    break
            elif data.startswith("LISTREQUEST"):
                _, peer_id = data.split('|')
                peers = get_peers_excluding(peer_id)
                peer_list_json = json.dumps(peers)
                try:
                    conn.sendall(peer_list_json.encode('utf-8'))
                    print(f"Sent peer list to peer {peer_id}")
                except Exception as e:
                    print(f"[ERROR] Error sending peer list: {e}")
                    break
        except Exception as e:
            print(f"[ERROR] {e}")
    print("A client has left!!!")
    conn.close()

# Function to run a server for tracker and listening to client from other host, port
def start_tracker(host='0.0.0.0', port=4000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind((host, port))
        print(f"Tracker running on {host}:{port}")
    except OSError as e:
        print(f"[ERROR] {e}. The port {port} might be already in use.")
        print("Please make sure no other process is using this port.")
        return
    
    server.listen()
    
    # Function to handle graceful shutdown
    def shutdown_gracefully(signal, frame):
        print("\n[INFO] Shutting down the tracker...")
        server.close()
        sys.exit(0)

    # Listen for termination signals to shut down gracefully
    signal.signal(signal.SIGINT, shutdown_gracefully)
    
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    # peer_1_infor = next((obj for obj in tracker_data if obj["peer_id"] == "2"), None) # find obj with peer_id = 2
    # print(tracker_data)
    start_tracker()
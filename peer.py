import socket
import sys
import json
import time

# pass a message to tracker
def register_with_tracker(tracker_host, tracker_port, peer_id, info_hash):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"REGISTER|{peer_id}|{info_hash}".encode('utf-8'))
            response = s.recv(1024)
            print(response.decode('utf-8'))
    except Exception as e:
        print(f"Error registering with tracker: {e}")
        
# Deregister a peer from the tracker
def deregister_from_tracker(tracker_host, tracker_port, peer_id):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"DISCONNECT|{peer_id}".encode('utf-8'))
            response = s.recv(1024)
            print(response.decode('utf-8'))
    except Exception as e:
        print(f"Error while deregistering: {e}")
        
# Request a peer list from the tracker
def request_peers_list(tracker_host, tracker_port, peer_id):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"LISTREQUEST|{peer_id}".encode('utf-8'))
            response = s.recv(1024)
            print(response.decode('utf-8'))
            time.sleep(5)
    except Exception as e:
        print(f"Error while requesting peers list: {e}")
        
        
if __name__ == "__main__":
    peer_id = sys.argv[1]
    # Configuration
    tracker_host = '192.168.1.104'
    tracker_port = 4000
    file = open(f'peer{peer_id}/torrent.json')
    peer_data = json.load(file)
    info = peer_data["info"] 
    info_hash = json.dumps(info, indent=4) # we get the info as string first, hash will be implemented later
    # Register with tracker
    register_with_tracker(tracker_host, tracker_port, peer_id, info_hash)
    try:
        while True:
            request_peers_list(tracker_host, tracker_port, peer_id)
            pass
    except KeyboardInterrupt:
        deregister_from_tracker(tracker_host, tracker_port, peer_id)
    # print(info_as_string)
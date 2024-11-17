import socket
import sys
import json
import time
import threading
import signal

# handle other peers connect, nhận request từ 1 peer khác
def handle_peer_connection(conn):
    try:
        data = conn.recv(1024).decode('utf-8')
        print(f"Message received: {data}")
        # Implement file-sharing logic or other communication here
        conn.sendall("Acknowledged".encode('utf-8'))
    except Exception as e:
        print(f"Error handling peer connection: {e}")
    finally:
        conn.close()

# create a peer server
def peer_server(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            host='0.0.0.0' # listening from all host
            server_socket.bind((host, port))
            server_socket.listen()
            print(f"Peer server listening on port {port}")
            while True:
                conn, addr = server_socket.accept()
                print(f"Connection received from {addr}")
                threading.Thread(target=handle_peer_connection, args=(conn,)).start()
    except Exception as e:
        print(f"Error in peer server: {e}")

# khi nhận được command, peer sẽ connect to other peers và nhận response
def connect_to_peer(peer_host, peer_port, message):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_host, peer_port))
            s.sendall(message.encode('utf-8'))
            response = s.recv(1024)
            print(f"Response from peer: {response.decode('utf-8')}")
    except Exception as e:
        print(f"Error connecting to peer: {e}")

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
            peers = json.loads(response.decode('utf-8'))
            print(peers)
            time.sleep(5)
    except Exception as e:
        print(f"Error while requesting peers list: {e}")
        
def shutdown_gracefully(signal, frame):
    print("\n[INFO] Shutting down the peer server...")
    sys.exit(0)
        
if __name__ == "__main__":
    peer_id = sys.argv[1]
    peer_port = int(sys.argv[2])
    # Configuration
    tracker_host = '192.168.1.104'
    tracker_port = 4000
    file = open(f'peer{peer_id}/torrent.json')
    peer_data = json.load(file)
    info = peer_data["info"] 
    info_hash = json.dumps(info, indent=4) # we get the info as string first, hash will be implemented later
    # Setup signal handling in the main thread
    signal.signal(signal.SIGINT, shutdown_gracefully)

    # Start peer server
    threading.Thread(target=peer_server, args=(peer_port,), daemon=True).start()
    
    # Register with tracker
    register_with_tracker(tracker_host, tracker_port, peer_id, info_hash)
    
    try:
        while True:
            # Listen for user commands
            print("Enter a command (CONNECT <peer_host> <peer_port> or EXIT):")
            command = input().strip()
            if command.startswith("CONNECT"):
                _, peer_host, peer_port = command.split()
                peer_port = int(peer_port)  # Convert to int
                message = f"Hello from peer {peer_id}!"
                connect_to_peer(peer_host, peer_port, message)
            elif command == "EXIT":
                print("Exiting...")
                deregister_from_tracker(tracker_host, tracker_port, peer_id)
                break
            request_peers_list(tracker_host, tracker_port, peer_id)
            pass
    except KeyboardInterrupt:
        deregister_from_tracker(tracker_host, tracker_port, peer_id)
    # print(info_as_string)
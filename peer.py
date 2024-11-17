import socket
import sys
import json
import os
import time
import threading
import signal

# Handle other peers' connections (e.g., file requests or messages)
def handle_peer_connection(conn):
    try:
        data = conn.recv(1024).decode('utf-8')
        print(f"Message received: {data}")

        # Check if it's a file transfer request
        if data.startswith("FILE_TRANSFER"):
            _, filename, peer_id = data.split('|')
            # Folder to store received files
            RECEIVED_FOLDER = "peer" + {peer_id}

            # Ensure the folder exists
            os.makedirs(RECEIVED_FOLDER, exist_ok=True)
            print(f"Preparing to receive file: {filename}")
            with open(os.path.join(RECEIVED_FOLDER, filename), 'wb') as f:
                while True:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    f.write(chunk)
            print(f"File {filename} received and saved to {RECEIVED_FOLDER}.")
            conn.sendall(f"File {filename} received successfully.".encode('utf-8'))
        else:
            conn.sendall("Acknowledged".encode('utf-8'))
    except Exception as e:
        print(f"Error handling peer connection: {e}")
    finally:
        conn.close()

# Create a peer server
def peer_server(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            host = '0.0.0.0'  # Listening from all hosts
            server_socket.bind((host, port))
            server_socket.listen()
            print(f"Peer server listening on port {port}")
            while True:
                conn, addr = server_socket.accept()
                print(f"Connection received from {addr}")
                threading.Thread(target=handle_peer_connection, args=(conn,)).start()
    except Exception as e:
        print(f"Error in peer server: {e}")

# Connect to other peers to send files or messages
def connect_to_peer(peer_host, peer_port, message):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_host, peer_port))
            s.sendall(message.encode('utf-8'))

            if message.startswith("FILE_TRANSFER"):
                _, filename = message.split('|')
                if os.path.exists(filename):
                    with open(filename, 'rb') as f:
                        while chunk := f.read(1024):
                            s.sendall(chunk)
                    print(f"File {filename} sent successfully.")
                else:
                    print(f"File {filename} does not exist.")
                    return
                s.shutdown(socket.SHUT_WR)  # Indicate file transfer is done

            response = s.recv(1024)
            print(f"Response from peer: {response.decode('utf-8')}")
    except Exception as e:
        print(f"Error connecting to peer: {e}")

# Pass a message to tracker
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
    info_hash = json.dumps(info, indent=4)  # We get the info as a string first, hash will be implemented later
    # Setup signal handling in the main thread
    signal.signal(signal.SIGINT, shutdown_gracefully)

    # Start peer server
    threading.Thread(target=peer_server, args=(peer_port,), daemon=True).start()

    # Register with tracker
    register_with_tracker(tracker_host, tracker_port, peer_id, info_hash)

    try:
        while True:
            # Listen for user commands
            print("Enter a command (CONNECT <peer_host> <peer_port> or SEND <peer_host> <peer_port> <peer_id> <file_path> or EXIT):")
            command = input().strip()
            if command.startswith("CONNECT"):
                _, peer_host, peer_port = command.split()
                peer_port = int(peer_port)
                message = f"Hello from peer {peer_id}!"
                connect_to_peer(peer_host, peer_port, message)
            elif command.startswith("SEND"):
                _, peer_host, peer_port, peer_id, file_path = command.split()
                peer_port = int(peer_port)
                message = f"FILE_TRANSFER|{os.path.basename(file_path)}|{peer_id}"
                connect_to_peer(peer_host, peer_port, message)
            elif command == "EXIT":
                print("Exiting...")
                deregister_from_tracker(tracker_host, tracker_port, peer_id)
                break
            request_peers_list(tracker_host, tracker_port, peer_id)
    except KeyboardInterrupt:
        deregister_from_tracker(tracker_host, tracker_port, peer_id)

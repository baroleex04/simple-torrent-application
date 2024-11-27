# tracker create a server
# peer connect to tracker and tracker write down a record of peer
import socket
import threading
import json
import signal
import sys

# Opening JSON file and load on tracker_data
file = open('tracker1/tracker.json')
tracker_data = json.load(file)

# Global dictionary to manage file locks
file_locks = {}

file_locks_lock = threading.Lock()

def get_file_lock(file_name):
    """
    Retrieve or create a lock for a specific file.
    """
    with file_locks_lock:  # Protect access to the file_locks dictionary
        if file_name not in file_locks:
            file_locks[file_name] = threading.Lock()
    return file_locks[file_name]

# Save the json file data
def save_tracker_data():
    """
    Save the current state of tracker data to the tracker.json file.

    This function ensures that any updates made to the tracker_data are 
    persisted to the tracker.json file on disk.

    Raises:
        IOError: If there is an issue writing to the file.
    """
    with open('tracker1/tracker.json', 'w') as file:
        json.dump(tracker_data, file, indent=4)
        
# def get_peers_excluding(peer_id):
#     """
#     Retrieve a list of all peers excluding the given peer ID.

#     Args:
#         peer_id (str): The peer ID to exclude from the returned list.

#     Returns:
#         list: A list of peers, each represented as a dictionary, excluding the given peer.
#     """
#     peers = []
#     for peer in tracker_data:
#         if peer["peer_id"] != peer_id:
#             peers.append(peer)
#     return peers

def get_peers_excluding(peer_id):
    """
    Retrieve a list of all peers excluding the given peer ID.
    """
    lock = threading.Lock()
    with lock:
        peers = [peer for peer in tracker_data if peer["peer_id"] != peer_id]
    return peers

def handle_register(conn, addr, data):
    """
    Handle the REGISTER command to add a new peer to the tracker.
    """
    try:
        _, peer_id, peer_port, info_hash = data.split('|')
        print(f"[REGISTER] Peer {peer_id} connected.")
        peer_ip = addr[0]
        info_hash_object = json.loads(info_hash)

        new_peer = {
            "info_hash": info_hash_object,
            "peer_id": peer_id,
            "port": peer_port,
            "uploaded": 20,
            "downloaded": 0,
            "left": 0,
            "compact": 1,
            "ip": peer_ip,
        }

        # Use a lock to ensure thread-safe modification of tracker_data
        lock = threading.Lock()
        with lock:
            if not any(obj["peer_id"] == peer_id for obj in tracker_data):
                tracker_data.append(new_peer)
                save_tracker_data()
                conn.sendall(f"REGISTERED|{peer_ip}".encode('utf-8'))
                print(f"[REGISTERED] Peer {peer_id} successfully registered.")
            else:
                conn.sendall(b"EXISTED PEER ID, CAN NOT REGISTERED")
    except Exception as e:
        print(f"[ERROR] Registering peer failed: {e}")
        conn.sendall(b"ERROR|Registering failed")

def handle_piece_info_request(conn, data):
    """
    Handle the PIECE_INFO_REQUEST command to return file piece mapping to peers.
    Uses file locks to prevent multiple simultaneous requests for the same file.
    """
    _, file_name = data.split("|")
    print(f"[PIECE INFO REQUEST] File requested: {file_name}")

    # Get the lock for the requested file
    file_lock = get_file_lock(file_name)

    try:
        if not file_lock.acquire(blocking=False):
            print(f"[LOCKED] File {file_name} is currently being downloaded. Request denied.")
            conn.sendall(b"ERROR|File is currently locked for another download")
            return

        # Process the request
        piece_to_peers = {}
        for peer in tracker_data:
            peer_ip = peer["ip"]
            peer_port = peer["port"]
            files = peer["info_hash"].get("files", [])
            for file in files:
                if file_name in file["path"]:
                    pieces = peer["info_hash"].get("pieces", [])
                    for piece in pieces:
                        piece_hash = piece["piece"]
                        if piece_hash not in piece_to_peers:
                            piece_to_peers[piece_hash] = []
                        piece_to_peers[piece_hash].append({"ip": peer_ip, "port": peer_port})

        piece_to_peers_json = json.dumps(piece_to_peers)
        conn.sendall(f"DATA_LENGTH|{len(piece_to_peers_json)}".encode('utf-8'))

        chunk_size = 4096
        for i in range(0, len(piece_to_peers_json), chunk_size):
            conn.sendall(piece_to_peers_json[i:i + chunk_size].encode('utf-8'))

        print(f"[SENT] Piece-to-peer mapping for file {file_name}")
    except Exception as e:
        print(f"[ERROR] Error sending piece info: {e}")
        conn.sendall(b"ERROR|Failed to retrieve piece info")
    finally:
        file_lock.release()
        print(f"[UNLOCKED] File {file_name} is now available for other peers.")

def handle_update_peer(conn, data):
    """
    Handle the UPDATE_PEER command to update peer info in the tracker.
    """
    peer_id = None  # Initialize to avoid unbound local variable issues
    try:
        print("[DEBUG] Updating peer")
        # print(f"Raw data received: {data}")
        
        # Split the header and validate parts
        parts = data.split('|', maxsplit=3)  # Limit to 3 splits to handle the JSON separately
        if len(parts) < 4:
            print("[ERROR] Malformed UPDATE_PEER command")
            conn.sendall(b"ERROR|Malformed UPDATE_PEER command")
            return
        
        command, peer_id, info_hash_length, remaining_data = data.split('|', maxsplit=3)
        info_hash_length = int(info_hash_length)

        received_data = remaining_data.encode('utf-8')
        while len(received_data) < info_hash_length:
            chunk = conn.recv(4096)
            if not chunk:
                print("[ERROR] Connection closed prematurely while receiving metadata")
                conn.sendall(b"ERROR|Incomplete metadata received")
                return
            received_data += chunk

        # Validate the received metadata length
        if len(received_data) != info_hash_length:
            print("[ERROR] Received metadata length does not match the expected size")
            conn.sendall(b"ERROR|Metadata length mismatch")
            return

        # Parse the JSON metadata
        try:
            info_hash_object = json.loads(received_data.decode('utf-8'))
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON received from peer {peer_id}: {e}")
            conn.sendall(b"ERROR|Invalid JSON format")
            return

        lock = threading.Lock()
        with lock:
            peer_to_update = next((obj for obj in tracker_data if obj["peer_id"] == peer_id), None)
            if peer_to_update:
                peer_to_update["info_hash"] = info_hash_object
                save_tracker_data()
                conn.sendall(f"UPDATED|{peer_id}".encode('utf-8'))
                print(f"[UPDATED] Peer {peer_id} info successfully updated.")
            else:
                conn.sendall(b"ERROR|Peer not found")
    except Exception as e:
        print(f"[ERROR] Updating peer info failed: {e}")
        conn.sendall(b"ERROR|Failed to update peer")

def handle_disconnect(conn, data):
    """
    Handle the DISCONNECT command to remove a peer from the tracker.
    """
    try:
        _, peer_id = data.split('|')
        print(f"[DISCONNECT] Peer {peer_id} requested to disconnect.")

        # Use a lock to ensure thread-safe modification of tracker_data
        lock = threading.Lock()
        with lock:
            peer_to_remove = next((obj for obj in tracker_data if obj["peer_id"] == peer_id), None)

            if not peer_to_remove:
                print(f"[ERROR] Peer {peer_id} not found in tracker data.")
                conn.sendall(b"ERROR|Peer ID not found")
                return

            # Remove the peer from the tracker data
            tracker_data.remove(peer_to_remove)
            save_tracker_data()
            conn.sendall(b"DISCONNECTED SUCCESSFULLY")
            print(f"[INFO] Peer {peer_id} successfully disconnected.")
    except Exception as e:
        print(f"[ERROR] Handling disconnect failed: {e}")
        conn.sendall(b"ERROR|Failed to disconnect peer")

def handle_list_request(conn, data):
    """
    Handle the LISTREQUEST command to provide a list of available peers to the requesting peer.
    """
    try:
        _, peer_id = data.split('|')
        print(f"[LISTREQUEST] Peer {peer_id} requested the peer list.")

        # Use a lock to ensure thread-safe read access to tracker_data
        lock = threading.Lock()
        with lock:
            peers = get_peers_excluding(peer_id)
            peer_list_json = json.dumps(peers)

        # Send the length of the data first
        conn.sendall(f"DATA_LENGTH|{len(peer_list_json)}".encode('utf-8'))

        # Send the actual peer list in chunks
        chunk_size = 4096
        for i in range(0, len(peer_list_json), chunk_size):
            conn.sendall(peer_list_json[i:i + chunk_size].encode('utf-8'))

        print(f"[INFO] Sent peer list to peer {peer_id}")
    except Exception as e:
        print(f"[ERROR] Handling list request failed: {e}")
        conn.sendall(b"ERROR|Failed to retrieve peer list")

# New 2
def handle_client(conn, addr):
    """
    Handle client connections and process requests from peers.
    Each client runs in its own thread, and commands are handled sequentially.
    """
    # print(f"[INFO] Connection established with {addr}")
    try:
        while True:
            # Read client request
            data = conn.recv(4096).decode('utf-8')
            if not data:
                break  # Client disconnected unexpectedly

            # Dispatch commands
            if data.startswith("REGISTER"):
                handle_register(conn, addr, data)
            elif data.startswith("PIECE_INFO_REQUEST"):
                handle_piece_info_request(conn, data)
            elif data.startswith("UPDATE_PEER"):
                handle_update_peer(conn, data)
            elif data.startswith("DISCONNECT"):
                handle_disconnect(conn, data)
                print(f"[INFO] Client {addr} disconnected gracefully")
                break  # Exit loop after handling DISCONNECT
            elif data.startswith("LISTREQUEST"):
                handle_list_request(conn, data)
            else:
                print(f"[ERROR] Unknown command from {addr}: {data}")
                conn.sendall(b"ERROR|Unknown command")
    except Exception as e:
        print(f"[ERROR] Exception occurred with client {addr}: {e}")
    finally:
        # print(f"[INFO] Closing connection with {addr}")
        conn.close()

def start_tracker(host='0.0.0.0', port=4000):
    """
    Start the tracker server to manage peer connections.

    The tracker listens for incoming connections from peers, processes their requests,
    and maintains an updated record of peers and their shared files.

    Args:
        host (str): The IP address to bind the tracker to. Defaults to '0.0.0.0' (all interfaces).
        port (int): The port to bind the tracker to. Defaults to 4000.

    Raises:
        OSError: If the port is already in use or there is an issue binding the tracker.
        SystemExit: On a graceful shutdown triggered by a signal.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind((host, port))
        # print(socket.gethostbyname_ex(socket.gethostname())[-1][1])
        print(f"Tracker running on {host}:{port}")
    except OSError as e:
        print(f"[ERROR] {e}. The port {port} might be already in use.")
        print("Please make sure no other process is using this port.")
        return
    
    server.listen()
    threads = []
    
    # Function to handle graceful shutdown
    def shutdown_gracefully(signal, frame):
        """
        Gracefully shut down the tracker server on receiving termination signals.

        Args:
            signal (int): The signal number received.
            frame: The current stack frame.
        """
        print("\n[INFO] Shutting down the tracker...")
        for thread in threads:
            thread.join()  # Ensure all threads finish
        server.close()
        sys.exit(0)

    # Listen for termination signals to shut down gracefully
    signal.signal(signal.SIGINT, shutdown_gracefully)
    
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))  # Create the thread
        thread.start()  # Start the thread
        threads.append(thread)  # Append the thread to the list for tracking


if __name__ == "__main__":
    # peer_1_infor = next((obj for obj in tracker_data if obj["peer_id"] == "2"), None) # find obj with peer_id = 2
    # print(tracker_data)
    start_tracker()
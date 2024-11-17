import socket
import threading

tracker_data = {}  # Format: {file_hash: [peer_addresses]}

def handle_client(conn, addr):
    try:
        data = conn.recv(1024).decode('utf-8')
        if data.startswith("REGISTER"):
            print(f"[REGISTER] Peer {addr} connected.")
            _, file_hash, peer_id = data.split('|')
            peer_addr = peer_id + "|" + str(addr)
            if file_hash not in tracker_data:
                tracker_data[file_hash] = []
            if peer_addr not in tracker_data[file_hash]:
                tracker_data[file_hash].append(peer_addr)
            conn.sendall(b"REGISTERED")
        elif data.startswith("DEREGISTER"):
            _, file_hash, peer_id = data.split('|')
            peer_addr = peer_id + "|" + str(addr) # Construct the string again
            if file_hash in tracker_data and peer_addr in tracker_data[file_hash]:
                tracker_data[file_hash].remove(peer_addr)
                print(f"[DEREGISTER] Peer {peer_addr} removed for file hash {file_hash}.")
                # Cleanup: Remove file_hash if no peers are left
                if not tracker_data[file_hash]:
                    print(f"[CLEANUP] No more peers for file hash {file_hash}. Removing entry.")
                    del tracker_data[file_hash]
            conn.sendall(b"DEREGISTERED")
        # elif data.startswith("QUERY"):
        #     print(f"[QUERY] Peer {addr} querying for file.")
        #     _, file_hash = data.split('|')
        #     peers = tracker_data.get(file_hash, [])
        #     conn.sendall('|'.join(peers).encode('utf-8'))
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        conn.close()

def start_tracker(host='0.0.0.0', port=4000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    print(f"Tracker running on {host}:{port}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_tracker()

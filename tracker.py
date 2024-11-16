import socket
import threading

tracker_data = {}  # Format: {file_hash: [peer_addresses]}

def handle_client(conn, addr):
    print(f"Connected by {addr}")
    try:
        data = conn.recv(1024).decode('utf-8')
        if data.startswith("REGISTER"):
            _, file_hash, peer_addr = data.split('|')
            if file_hash not in tracker_data:
                tracker_data[file_hash] = []
            if peer_addr not in tracker_data[file_hash]:
                tracker_data[file_hash].append(peer_addr)
            conn.sendall(b"REGISTERED")
        elif data.startswith("QUERY"):
            _, file_hash = data.split('|')
            peers = tracker_data.get(file_hash, [])
            conn.sendall('|'.join(peers).encode('utf-8'))
        elif data.startswith("DEREGISTER"):
            _, file_hash, peer_addr = data.split('|')
            if file_hash in tracker_data and peer_addr in tracker_data[file_hash]:
                tracker_data[file_hash].remove(peer_addr)
                # Cleanup: Remove file_hash if no peers are left
                if not tracker_data[file_hash]:
                    del tracker_data[file_hash]
            conn.sendall(b"DEREGISTERED")
    finally:
        conn.close()

def start_tracker(host='0.0.0.0', port=6881):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    print(f"Tracker running on {host}:{port}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_tracker()

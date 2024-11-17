import socket
import threading
import atexit
import signal
import sys

# Register a peer with the tracker
def register_with_tracker(tracker_host, tracker_port, file_hash, peer_id):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"REGISTER|{file_hash}|{peer_id}".encode('utf-8'))
            response = s.recv(1024)
            print(response.decode('utf-8'))
    except Exception as e:
        print(f"Error registering with tracker: {e}")

# Deregister a peer from the tracker
def deregister_from_tracker(tracker_host, tracker_port, file_hash, peer_id):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"DEREGISTER|{file_hash}|{peer_id}".encode('utf-8'))
            response = s.recv(1024)
            print(response.decode('utf-8'))
    except Exception as e:
        print(f"Error while deregistering: {e}")

# Cleanup function for deregistration
def create_cleanup(tracker_host, tracker_port, file_hash, peer_id):
    def cleanup():
        print("Exiting and deregistering from tracker...")
        try:
            deregister_from_tracker(tracker_host, tracker_port, file_hash, peer_id)
        except Exception as e:
            print(f"Error during cleanup: {e}")
    return cleanup

# Query peers for a specific file
def query_peers(tracker_host, tracker_port, file_hash):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"QUERY|{file_hash}".encode('utf-8'))
            response = s.recv(1024).decode('utf-8')
            return response.split('|')
    except Exception as e:
        print(f"Error querying peers: {e}")
        return []

# Serve a file to peers
def serve_file(file_path, host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    print(f"Serving file on {host}:{port}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=send_file, args=(conn, file_path)).start()

# Send file chunks to a connected peer
def send_file(conn, file_path):
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(1024):
                conn.sendall(chunk)
    finally:
        conn.close()

# Download a file from a peer
def download_file(peer, file_path):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(peer)
            with open(file_path, 'wb') as f:
                while chunk := s.recv(1024):
                    f.write(chunk)
    except Exception as e:
        print(f"Error downloading file: {e}")

# Signal handler for CTRL+C
shutdown_flag = False

def signal_handler(sig, frame):
    global shutdown_flag
    print("Caught interrupt signal, shutting down...")
    shutdown_flag = True

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    peer_id = sys.argv[1]
    # Configuration
    tracker_host = '192.168.1.102'
    tracker_port = 4000
    file_hash = 'example_hash' + peer_id
    peer_host = '0.0.0.0'  # Allow connections from external devices
    peer_port = 4000 + int(peer_id)
    file_path = 'example_file.txt' # List of file_hash

    # Register cleanup with atexit
    atexit.register(create_cleanup(tracker_host, tracker_port, file_hash, peer_id))

    # Register with tracker
    register_with_tracker(tracker_host, tracker_port, file_hash, peer_id)

    # Start serving the file
    threading.Thread(target=serve_file, args=(file_path, peer_host, peer_port)).start()

    # Example: Query peers and download (commented for manual use)
    # peers = query_peers(tracker_host, tracker_port, file_hash)
    # if peers:
    #     peer_host, peer_port = peers[0].split(':')
    #     download_file((peer_host, int(peer_port)), 'downloaded_file.txt')

    # Simulate running until interrupted
    try:
        while True:
            pass
    except KeyboardInterrupt:
        pass

import socket
import threading
import os

def register_with_tracker(tracker_host, tracker_port, file_hash, peer_address):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((tracker_host, tracker_port))
        s.sendall(f"REGISTER|{file_hash}|{peer_address}".encode('utf-8'))
        response = s.recv(1024)
        print(response.decode('utf-8'))

def query_peers(tracker_host, tracker_port, file_hash):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((tracker_host, tracker_port))
        s.sendall(f"QUERY|{file_hash}".encode('utf-8'))
        response = s.recv(1024).decode('utf-8')
        return response.split('|')

def serve_file(file_path, host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    print(f"Serving file on {host}:{port}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=send_file, args=(conn, file_path)).start()

def send_file(conn, file_path):
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(1024):
                conn.sendall(chunk)
    finally:
        conn.close()

def download_file(peer, file_path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(peer)
        with open(file_path, 'wb') as f:
            while chunk := s.recv(1024):
                f.write(chunk)

if __name__ == "__main__":
    # Example usage
    tracker_host = '127.0.0.1'
    tracker_port = 6881
    file_hash = 'example_hash'
    peer_host = '127.0.0.1'
    peer_port = 6882
    file_path = 'example_file.txt'

    # Register with tracker
    register_with_tracker(tracker_host, tracker_port, file_hash, f"{peer_host}:{peer_port}")

    # Serve the file
    threading.Thread(target=serve_file, args=(file_path, peer_host, peer_port)).start()

    # Query for peers and download
    peers = query_peers(tracker_host, tracker_port, file_hash)
    if peers:
        peer_host, peer_port = peers[0].split(':')
        download_file((peer_host, int(peer_port)), 'downloaded_file.txt')

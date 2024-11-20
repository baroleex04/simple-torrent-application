import socket
import sys
import json
import os
import time
import threading
import signal
import hashlib

def update_torrent_json(peer_id, file_path, chunk_size):
    """Update the torrent.json file after uploading a file."""
    try:
        # Read the current torrent.json
        torrent_path = f"peer{peer_id}/torrent.json"
        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)

        # Compute the file metadata
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_chunks = []

        # Generate hashes for each chunk
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                file_chunks.append({"piece": hashlib.sha1(chunk).hexdigest()})

        # Update the pieces list
        torrent_data['info']['pieces'].extend(file_chunks)

        # Update the files list
        file_metadata = {
            "path": [f"peer{peer_id}", file_name],
            "length": file_size
        }
        torrent_data['info']['files'].append(file_metadata)

        # Save the updated torrent.json
        with open(torrent_path, 'w') as torrent_file:
            json.dump(torrent_data, torrent_file, indent=4)

        print(f"Updated torrent.json for peer {peer_id} with file {file_name}.")
    except FileNotFoundError:
        print(f"Error: torrent.json not found for peer {peer_id}.")
    except Exception as e:
        print(f"Error updating torrent.json: {e}")
        
# function to handle splitting file
def split_file(file_path, chunk_size):
    """Splits a file into smaller pieces."""
    try:
        with open(file_path, 'rb') as f:
            file_name = os.path.basename(file_path)
            part_num = 0
            while chunk := f.read(chunk_size):
                part_file_name = f"{part_num}_{file_name}"
                with open(part_file_name, 'wb') as part_file:
                    part_file.write(chunk)
                print(f"Created: {part_file_name}")
                part_num += 1
    except FileNotFoundError:
        print("File not found. Please provide a valid file path.")
    except Exception as e:
        print(f"An error occurred: {e}")

# function to handle combining files
def combine_files(part_files, output_file):
    """Combines smaller pieces into the original file."""
    try:
        with open(output_file, 'wb') as output:
            for part_file in part_files:
                with open(part_file, 'rb') as f:
                    output.write(f.read())
                print(f"Added: {part_file}")
        print(f"File combined into: {output_file}")
    except FileNotFoundError:
        print("One or more part files not found. Please provide valid file paths.")
    except Exception as e:
        print(f"An error occurred: {e}")

# function to upload a file on a peer
# Function to handle uploading a file and splitting it
def upload_file(peer_id, file_path, chunk_size=1024):
    """Uploads a file by splitting it into chunks and storing them locally."""
    try:
        # Create a folder for storing chunks for this peer
        chunks_folder = f"peer{peer_id}/chunks"
        os.makedirs(chunks_folder, exist_ok=True)
        
        # Split the file into chunks
        with open(file_path, 'rb') as f:
            file_name = os.path.basename(file_path)
            part_num = 0
            while chunk := f.read(chunk_size):
                part_file_name = os.path.join(chunks_folder, f"{part_num}_{file_name}")
                with open(part_file_name, 'wb') as part_file:
                    part_file.write(chunk)
                print(f"Stored chunk: {part_file_name}")
                part_num += 1
        
        print(f"File {file_name} has been split and stored in {chunks_folder}.")
    except FileNotFoundError:
        print("File not found. Please provide a valid file path.")
    except Exception as e:
        print(f"An error occurred while uploading the file: {e}")
    
# Handle other peers' connections (e.g., file requests or messages)
def handle_peer_connection(conn, peer_id):
    try:
        data = conn.recv(1024).decode('utf-8')
        print(f"Message received: {data}")
        if data.startswith("UPLOAD_FILE"):
            # Extract the file name and initiate upload process
            _, file_name, chunk_size = data.split('|')
            chunk_size = int(chunk_size)
            received_folder = f"peer{peer_id}/uploaded_files"
            os.makedirs(received_folder, exist_ok=True)
            file_path = os.path.join(received_folder, file_name)
            
            print(f"Uploading file: {file_name} with chunk size {chunk_size}")
            with open(file_path, 'wb') as f:
                while True:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    f.write(chunk)
            print(f"File {file_name} was uploaded at {file_path}")
            
            # Split the file into chunks for storage
            upload_file(peer_id, file_path, chunk_size)
            conn.sendall(f"File {file_name} uploaded and split successfully.".encode('utf-8'))
        if data.startswith("FILE_TRANSFER"):
            _, file_name = data.split('|')

            # Acknowledge readiness to receive the file
            conn.sendall("READY".encode('utf-8'))

            # Folder to store received files
            received_folder = f"peer{peer_id}/received_files"
            os.makedirs(received_folder, exist_ok=True)
            file_path = os.path.join(received_folder, file_name)

            print(f"Preparing to receive file: {file_name}")
            
            # Open the file in write mode
            with open(file_path, 'wb') as f:
                while True:
                    chunk = conn.recv(1024)
                    if not chunk:  # End of file
                        break
                    f.write(chunk)

            print(f"File {file_name} received and saved to {received_folder}.")
            
            # Send confirmation back to the sender
            conn.sendall(f"File {file_name} received successfully.".encode('utf-8'))
        else:
            print(f"Unknown message received: {data}")
            conn.sendall("Invalid request".encode('utf-8'))
    except Exception as e:
        print(f"Error handling peer connection: {e}")
    finally:
        conn.close()

# Create a peer server
def peer_server(port,peer_id):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            host = '0.0.0.0'  # Listening from all hosts
            server_socket.bind((host, port))
            server_socket.listen()
            print(f"Peer server listening on port {port}")
            while True:
                conn, addr = server_socket.accept()
                print(f"Connection received from {addr}")
                threading.Thread(target=handle_peer_connection, args=(conn,peer_id)).start()
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
            response = s.recv(1024).decode('utf-8')
            print(response)
            _, peer_host = response.split('|')
            return peer_host
    except Exception as e:
        print(f"Error registering with tracker: {e}")
        return

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
        
# Send a file to another peer
def send_file_to_peer(peer_host, peer_port, peer_id, file_name):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_host, peer_port))

            # Construct the full file path
            file_path = f"peer{peer_id}/{file_name}"

            # Check if the file exists
            if os.path.exists(file_path):
                # Send metadata (file name) first
                s.sendall(f"FILE_TRANSFER|{file_name}".encode('utf-8'))
                response = s.recv(1024).decode('utf-8')
                if response != "READY":
                    print(f"Peer not ready for file transfer: {response}")
                    return

                # Send the file content
                with open(file_path, 'rb') as f:
                    while chunk := f.read(1024):
                        s.sendall(chunk)

                print(f"File {file_name} sent successfully to peer {peer_host}:{peer_port}.")
                s.shutdown(socket.SHUT_WR)  # Indicate transfer complete

                # Await confirmation
                response = s.recv(1024)
                print(f"Response from peer: {response.decode('utf-8')}")
            else:
                print(f"Error: File {file_path} does not exist.")
    except Exception as e:
        print(f"Error sending file to peer: {e}")



def shutdown_gracefully(signal, frame):
    print("\n[INFO] Shutting down the peer server...")
    sys.exit(0)

if __name__ == "__main__":
    peer_id = sys.argv[1]
    peer_port = int(sys.argv[2])
    # Configuration
    tracker_host = '192.168.1.109'
    # tracker_host = '10.128.236.22'
    tracker_port = 4000
    file = open(f'peer{peer_id}/torrent.json')
    peer_data = json.load(file)
    info = peer_data["info"]
    chunk_size = info["piece length"]
    info_hash = json.dumps(info, indent=4)  # We get the info as a string first, hash will be implemented later
    # Setup signal handling in the main thread
    signal.signal(signal.SIGINT, shutdown_gracefully)

    # Start peer server
    threading.Thread(target=peer_server, args=(peer_port,peer_id), daemon=True).start()

    # Register with tracker
    peer_host = register_with_tracker(tracker_host, tracker_port, peer_id, info_hash)

    try:
        while True:
            # Listen for user commands
            print("Enter a command (CONNECT <peer_host> <peer_port> or SEND <peer_host> <peer_port> <file_name> or UPLOAD <file_path> or EXIT):")
            command = input().strip()
            if command.startswith("CONNECT"):
                _, peer_host, peer_port = command.split()
                peer_port = int(peer_port)
                message = f"Hello from peer {peer_id}!"
                connect_to_peer(peer_host, peer_port, message)
            if command.startswith("SEND"):
                _, peer_host, peer_port, file_name = command.split()
                peer_port = int(peer_port)
                send_file_to_peer(peer_host, peer_port, peer_id, file_name)
            if command.startswith("UPLOAD"):
                _, file_path = command.split()
                if os.path.exists(file_path):
                    print(f"Uploading file: {file_path}...")
                    # Use the upload_file function to split and store locally
                    upload_file(peer_id, file_path, chunk_size)
                    # Update the torrent.json
                    update_torrent_json(peer_id, file_path, chunk_size)
                    print("File upload complete.")
                else:
                    print(f"Error: File {file_path} does not exist.")
            elif command == "EXIT":
                print("Exiting...")
                deregister_from_tracker(tracker_host, tracker_port, peer_id)
                break
            request_peers_list(tracker_host, tracker_port, peer_id)
    except KeyboardInterrupt:
        deregister_from_tracker(tracker_host, tracker_port, peer_id)

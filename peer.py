import socket
import sys
import json
import os
import time
import threading
import signal
import hashlib
from datetime import datetime

# tracker_host = '192.168.1.109'
tracker_host = '192.168.1.6'
# tracker_host = '10.128.236.22'
tracker_port = 4000
download_tracker = set()

def compute_chunk_hash(chunk_data, chunk_index, file_name):
    """Compute a unique hash for a chunk based on its content, index, and file name."""
    unique_data = chunk_data + chunk_index.to_bytes(4, byteorder='big') + file_name.encode('utf-8')
    return hashlib.sha1(unique_data).hexdigest()

# download piece from peer
def download_piece_from_peer(peer_host, peer_port, piece_hash, output_path, retry_peers=[], peer_id=None, file_name=None, chunk_index=None):
    """Download a specific piece from a peer, retrying with other peers if needed."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            start_time = datetime.now()
            print(f"[{start_time.strftime('%H:%M:%S.%f')}] Starting download of piece {piece_hash} from {peer_host}:{peer_port}")
            s.connect((peer_host, int(peer_port)))  # Ensure port is an integer
            request_message = f"REQUEST_PIECE|{piece_hash}"
            s.sendall(request_message.encode('utf-8'))

            with open(output_path, 'wb') as output_file:
                while chunk := s.recv(1024):
                    output_file.write(chunk)

            end_time = datetime.now()
            print(f"[{end_time.strftime('%H:%M:%S.%f')}] Finished download of piece {piece_hash} from {peer_host}:{peer_port}")
            print(f"Duration: {(end_time - start_time).total_seconds()} seconds")
            print(f"Downloaded piece {piece_hash} from {peer_host}:{peer_port}")

            # Validate the downloaded piece
            with open(output_path, 'rb') as output_file:
                downloaded_data = output_file.read()
                downloaded_hash = compute_chunk_hash(downloaded_data, chunk_index, file_name)
                if downloaded_hash != piece_hash:
                    print(f"Hash mismatch: expected {piece_hash}, got {downloaded_hash}")
                    raise ValueError("Downloaded chunk hash does not match the expected hash.")
            
            if peer_id is not None and file_name is not None:
                update_torrent_with_chunks(peer_id, file_name)
    except Exception as e:
        print(f"Error downloading piece: {e}")

def update_torrent_with_chunks(peer_id, file_name=None):
    """Update the torrent.json file with information from the chunks folder."""
    try:
        torrent_path = f"peer{peer_id}/torrent.json"
        chunks_path = f"peer{peer_id}/chunks"
        received_files_path = f"peer{peer_id}/received_files"

        if not os.path.exists(torrent_path):
            print(f"Error: {torrent_path} not found.")
            return

        if not os.path.exists(chunks_path):
            print(f"Error: {chunks_path} not found.")
            return

        # Load the current torrent.json content
        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)

        # Ensure pieces structure exists
        if "info" not in torrent_data or "pieces" not in torrent_data["info"]:
            print(f"Error: Invalid torrent.json structure in {torrent_path}.")
            return

        existing_pieces = {piece["piece"] for piece in torrent_data["info"]["pieces"]}
        updated_pieces = []

        # Read all chunks and update torrent.json
        for chunk_file in sorted(os.listdir(chunks_path)):
            chunk_hash, _ = os.path.splitext(chunk_file)
            if chunk_hash not in existing_pieces:
                updated_pieces.append({"piece": chunk_hash})
                print(f"Added new piece {chunk_hash} to torrent.json.")
    
        # Add new pieces to the torrent data
        torrent_data["info"]["pieces"].extend(updated_pieces)

        # Update the files list if file_name is provided
        if file_name:
            received_file_path = os.path.join(received_files_path, file_name)
            if os.path.exists(received_file_path):
                file_metadata = {
                    "path": [f"peer{peer_id}", file_name],
                    "length": os.path.getsize(received_file_path)
                }
                if file_metadata not in torrent_data["info"]["files"]:
                    torrent_data["info"]["files"].append(file_metadata)
                    print(f"Added file metadata: {file_metadata}")
        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)
        new_info_hash = torrent_data["info"]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((tracker_host, tracker_port))
                print(f"Update peer hereee: {peer_id}")
                update_message = f"UPDATE_PEER|{peer_id}|{json.dumps(new_info_hash)}"
                s.sendall(update_message.encode('utf-8'))
                response = s.recv(1024).decode('utf-8')
                print(f"Tracker response: {response}")
        except Exception as e:
            print(f"Error notifying tracker: {e}")
            print("Update on tracker completed.")
        # Save the updated torrent.json
        with open(torrent_path, 'w') as torrent_file:
            json.dump(torrent_data, torrent_file, indent=4)
            print(f"Torrent.json updated successfully for peer {peer_id}.")
    except Exception as e:
        print(f"Error updating torrent.json: {e}")

# download pieces concurrently
def download_file_concurrently(peer_id, file_name, pieces_to_peers, chunk_size):
    """Download file pieces from multiple peers concurrently."""
    chunk_folder = f"peer{peer_id}/chunks"
    os.makedirs(chunk_folder, exist_ok=True)

    threads = []
    piece_order = list(pieces_to_peers.keys())  # Preserve the correct order of pieces

    # Distribute pieces across peers using round-robin
    for chunk_index, (piece_hash, peers) in enumerate(pieces_to_peers.items()):
        if piece_hash in download_tracker:
            print(f"Skipping already downloaded piece: {piece_hash}")
            continue

        # Select a peer for the current piece using round-robin
        selected_peer = peers[chunk_index % len(peers)]
        peer_host = selected_peer["ip"]
        peer_port = selected_peer["port"]

        output_path = os.path.join(chunk_folder, f"{piece_hash}.chunk")
        thread = threading.Thread(
            target=download_piece_from_peer,
            args=(peer_host, peer_port, piece_hash, output_path, peers[1:], peer_id, file_name, chunk_index)
        )
        threads.append(thread)
        download_tracker.add(piece_hash)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print("All pieces downloaded. Combining...")
    combine_and_validate_pieces(chunk_folder, f"peer{peer_id}/received_files/{file_name}", piece_order, file_name)

def request_pieces_info(tracker_host, tracker_port, file_name):
    """Request peers list for each piece from the tracker."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            request_message = f"PIECE_INFO_REQUEST|{file_name}"
            s.sendall(request_message.encode('utf-8'))
            
            response = s.recv(4096)
            pieces_to_peers = json.loads(response.decode('utf-8'))
            if not pieces_to_peers:
                print(f"[INFO] No pieces found for file '{file_name}'.")
                return {}
            print(f"Received pieces-to-peers mapping: {pieces_to_peers}")
            return pieces_to_peers
    except Exception as e:
        print(f"Error requesting piece info: {e}")
        return {}

def update_torrent_json(peer_id, file_path, chunk_size):
    """Update the torrent.json file after uploading a file."""
    try:
        torrent_path = f"peer{peer_id}/torrent.json"
        chunks_folder = f"peer{peer_id}/chunks"

        if not os.path.exists(torrent_path):
            print(f"Error: {torrent_path} not found.")
            return None

        if not os.path.exists(chunks_folder):
            os.makedirs(chunks_folder, exist_ok=True)

        # Load the current torrent.json content
        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)

        # Prepare file metadata
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_metadata = {
            "path": [f"peer{peer_id}", file_name],
            "length": file_size
        }

        # Add file metadata if not already present
        if file_metadata not in torrent_data["info"]["files"]:
            torrent_data["info"]["files"].append(file_metadata)

        # Compute hashes for each chunk and update the pieces list
        # updated_pieces = []
        updated_pieces = torrent_data["info"]["pieces"]
        with open(file_path, 'rb') as f:
            chunk_index = 0
            while chunk := f.read(chunk_size):
                piece_hash = compute_chunk_hash(chunk, chunk_index, file_name)
                if piece_hash not in updated_pieces:
                    updated_pieces.append({"piece": piece_hash})
                    # Save the chunk to the chunks folder
                    chunk_file_path = os.path.join(chunks_folder, f"{piece_hash}.chunk")
                    with open(chunk_file_path, 'wb') as chunk_file:
                        chunk_file.write(chunk)
                    print(f"Stored chunk: {chunk_file_path} with hash {piece_hash}")
                    chunk_index += 1

        # Update the pieces array
        torrent_data["info"]["pieces"] = updated_pieces

        # Save the updated torrent.json
        with open(torrent_path, 'w') as torrent_file:
            json.dump(torrent_data, torrent_file, indent=4)

        return torrent_data["info"]
    except Exception as e:
        print(f"Error updating torrent.json: {e}")
        return None
        
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

# Function to handle uploading a file and splitting it
def upload_file(peer_id, file_path, chunk_size=1024):
    """Uploads a file by splitting it into chunks and storing them locally."""
    try:
        chunks_folder = f"peer{peer_id}/chunks"
        os.makedirs(chunks_folder, exist_ok=True)

        file_name = os.path.basename(file_path)
        piece_order = []

        with open(file_path, 'rb') as f:
            chunk_index = 0  # Start with the first chunk index
            while chunk := f.read(chunk_size):
                # Compute a unique hash for each chunk
                piece_hash = compute_chunk_hash(chunk, chunk_index, file_name)
                part_file_name = os.path.join(chunks_folder, f"{piece_hash}.chunk")
                with open(part_file_name, 'wb') as part_file:
                    part_file.write(chunk)
                piece_order.append(piece_hash)
                print(f"Stored chunk: {part_file_name} with hash {piece_hash}")
                chunk_index += 1  # Increment the chunk index

        print(f"Piece order: {piece_order}")
    except Exception as e:
        print(f"Error uploading file: {e}")
        
def validate_chunk(chunk_data, chunk_index, expected_hash, file_name):
    """Validate that a chunk matches its expected hash."""
    actual_hash = compute_chunk_hash(chunk_data, chunk_index, file_name)
    return actual_hash == expected_hash

def combine_and_validate_pieces(received_folder, output_file, piece_order, file_name):
    """Combine pieces into a file and validate its integrity."""
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'wb') as output:
            for chunk_index, piece_hash in enumerate(piece_order):
                piece_path = os.path.join(received_folder, f"{piece_hash}.chunk")
                if os.path.exists(piece_path):
                    with open(piece_path, 'rb') as pf:
                        content = pf.read()
                        # Validate the chunk hash before combining
                        if not validate_chunk(content, chunk_index, piece_hash, file_name):
                            print(f"[DEBUG] Validation failed for chunk {chunk_index}: {piece_hash}")
                            print(f"[DEBUG] File name: {file_name}, Content length: {len(content)}")
                            print(f"Error: Piece {piece_hash} did not pass validation!")
                            continue
                        output.write(content)
                        print(f"Added piece {piece_hash} to the output file.")
                else:
                    print(f"Missing piece: {piece_hash}. File may be incomplete.")
        
        print(f"File combined into {output_file} successfully.")
        
        # Update the torrent.json with the new file metadata
        peer_id = output_file.split('/')[0].replace("peer", "")  # Extract peer ID
        file_name = os.path.basename(output_file)
        file_size = os.path.getsize(output_file)

        torrent_path = f"peer{peer_id}/torrent.json"
        if not os.path.exists(torrent_path):
            print(f"Error: {torrent_path} not found.")
            return

        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)

        # Add file metadata if not already present
        file_metadata = {
            "path": [f"peer{peer_id}", file_name],
            "length": file_size
        }
        if file_metadata not in torrent_data["info"]["files"]:
            torrent_data["info"]["files"].append(file_metadata)
            print(f"Added file metadata to torrent.json: {file_metadata}")

        # Save updated torrent.json
        with open(torrent_path, 'w') as torrent_file:
            json.dump(torrent_data, torrent_file, indent=4)
            print(f"Updated torrent.json successfully for peer {peer_id}.")
    except Exception as e:
        print(f"Error combining pieces: {e}")

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
        if data.startswith("REQUEST_PIECE"):
            _, piece_hash = data.split('|')
            piece_path = os.path.join(f"peer{peer_id}/chunks", f"{piece_hash}.chunk")
            if os.path.exists(piece_path):
                with open(piece_path, 'rb') as piece_file:
                    piece_data = piece_file.read()
                    conn.sendall(piece_data)
                print(f"Sent piece {piece_hash} to peer.")
            else:
                conn.sendall("PIECE_NOT_FOUND".encode('utf-8'))
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
def register_with_tracker(tracker_host, tracker_port, peer_id, peer_port, info_hash):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"REGISTER|{peer_id}|{peer_port}|{info_hash}".encode('utf-8'))
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
            response = s.recv(4096)
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
    peer_host = register_with_tracker(tracker_host, tracker_port, peer_id, peer_port, info_hash)

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
            if command.startswith("UPLOAD"):
                _, file_path = command.split()
                if os.path.exists(file_path):
                    print(f"Uploading file: {file_path}...")
                    # Use the upload_file function to split and store locally
                    upload_file(peer_id, file_path, chunk_size)
                    # Update the torrent.json and compute the new info_hash
                    new_info_hash = update_torrent_json(peer_id, file_path, chunk_size)
                    if new_info_hash:
                    # Notify the tracker about the updated info_hash
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.connect((tracker_host, tracker_port))
                                print(f"Update peer hereee: {peer_id}")
                                update_message = f"UPDATE_PEER|{peer_id}|{json.dumps(new_info_hash)}"
                                s.sendall(update_message.encode('utf-8'))
                                response = s.recv(1024).decode('utf-8')
                                print(f"Tracker response: {response}")
                        except Exception as e:
                            print(f"Error notifying tracker: {e}")
                            print("File upload complete.")
                    else:
                        print(f"Error: File {file_path} does not exist.")
            if command.startswith("DOWNLOAD"):
                _, file_name = command.split()
                pieces_to_peers = request_pieces_info(tracker_host, tracker_port, file_name)
                if pieces_to_peers:
                    download_file_concurrently(peer_id, file_name, pieces_to_peers, chunk_size)
                else:
                    print("No piece info available for download.")
            elif command == "EXIT":
                print("Exiting...")
                deregister_from_tracker(tracker_host, tracker_port, peer_id)
                break
            request_peers_list(tracker_host, tracker_port, peer_id)
    except KeyboardInterrupt:
        deregister_from_tracker(tracker_host, tracker_port, peer_id)

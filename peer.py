import socket
import sys
import json
import os
import time
import threading
import signal
import hashlib
from datetime import datetime

# tracker_host = '192.168.0.73'
tracker_host = '192.168.1.4'
# tracker_host = '192.168.1.109'
# tracker_host = '10.128.236.22'
tracker_port = 4000
download_tracker = set()

file_lock = threading.Lock()

def compute_chunk_hash(chunk_data, chunk_index):
    """
    Compute a unique hash for a chunk.

    Args:
        chunk_data (bytes): The data of the chunk.
        chunk_index (int): The index of the chunk.

    Returns:
        str: SHA-1 hash of the chunk combined with its index.
    """
    unique_data = chunk_data + chunk_index.to_bytes(4, byteorder='big')  # Append the index as 4 bytes
    return hashlib.sha1(unique_data).hexdigest()

def compute_chunk_hash_3(chunk_data, chunk_index, file_name):
    """
    Compute a unique hash for a chunk.

    Args:
        chunk_data (bytes): The data of the chunk.
        chunk_index (int): The index of the chunk.
        file_name (str): The name of the file being processed.

    Returns:
        str: The SHA-1 hash of the chunk combined with the file name and index.
    """
    unique_data = file_name.encode('utf-8') + chunk_index.to_bytes(4, byteorder='big') + chunk_data
    return hashlib.sha1(unique_data).hexdigest()

def download_piece_from_peer(peer_host, peer_port, piece_hash, output_path, retry_peers=[], peer_id=None, file_name=None, chunk_index=None):
    """
    Download a specific piece from a peer.

    Args:
        peer_host (str): The IP address of the peer.
        peer_port (int): The port number of the peer.
        piece_hash (str): The hash of the piece to be downloaded.
        output_path (str): Path to save the downloaded piece.
        retry_peers (list): A list of alternative peers to try in case of failure.
        peer_id (str, optional): The ID of the current peer.
        file_name (str, optional): Name of the file being downloaded.
        chunk_index (int, optional): Index of the current piece.

    Raises:
        ValueError: If the downloaded chunk hash does not match the expected hash.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            start_time = datetime.now()
            print(f"[{start_time.strftime('%H:%M:%S.%f')}] Starting download of piece {piece_hash} from {peer_host}:{peer_port}")
            s.connect((peer_host, int(peer_port)))  # Ensure port is an integer
            request_message = f"REQUEST_PIECE|{piece_hash}"
            s.sendall(request_message.encode('utf-8'))

            # Safely write the downloaded chunk to the file
            with file_lock:
                with open(output_path, 'wb') as output_file:
                    while chunk := s.recv(1024):
                        output_file.write(chunk)

            end_time = datetime.now()
            print(f"[{end_time.strftime('%H:%M:%S.%f')}] Finished download of piece {piece_hash} from {peer_host}:{peer_port}")
            print(f"Duration: {(end_time - start_time).total_seconds()} seconds")
            print(f"Downloaded piece {piece_hash} from {peer_host}:{peer_port}")

            # Validate the downloaded chunk
            with file_lock:
                with open(output_path, 'rb') as output_file:
                    downloaded_data = output_file.read()
                    downloaded_hash = compute_chunk_hash_3(downloaded_data, chunk_index, file_name)
                    if downloaded_hash != piece_hash:
                        print(f"Hash mismatch: expected {piece_hash}, got {downloaded_hash}")
                        raise ValueError("Downloaded chunk hash does not match the expected hash.")
            
            if peer_id is not None and file_name is not None:
                update_torrent_with_chunks(peer_id, file_name)
    except Exception as e:
        print(f"Error downloading piece: {e}")

def update_torrent_with_chunks(peer_id, file_name=None):
    """
    Update the torrent.json file with new chunk information.

    Args:
        peer_id (str): ID of the peer.
        file_name (str, optional): Name of the file being updated in the torrent file.

    Raises:
        FileNotFoundError: If the torrent.json file or chunks directory is not found.
        ValueError: If the torrent.json structure is invalid.
    """
    try:
        torrent_path = f"peer{peer_id}/torrent.json"
        if not os.path.exists(torrent_path):
            print(f"Torrent file not found: {torrent_path}")
            return

        chunks_path = f"peer{peer_id}/chunks"
        received_files_path = f"peer{peer_id}/received_files"

        if not os.path.exists(chunks_path):
            print(f"Error: {chunks_path} not found.")
            return

        # Safely load and update the torrent.json file
        with file_lock:
            with open(torrent_path, 'r') as torrent_file:
                torrent_data = json.load(torrent_file)

            # Ensure pieces structure exists
            if "info" not in torrent_data or "pieces" not in torrent_data["info"]:
                print(f"Error: Invalid torrent.json structure in {torrent_path}.")
                return

            existing_pieces = {piece["piece"] for piece in torrent_data["info"]["pieces"]}
            updated_pieces = []

            for chunk_file in sorted(os.listdir(chunks_path)):
                chunk_hash, _ = os.path.splitext(chunk_file)
                if chunk_hash not in existing_pieces:
                    updated_pieces.append({"piece": chunk_hash})

            torrent_data["info"]["pieces"].extend(updated_pieces)

            if file_name:
                received_file_path = os.path.join(received_files_path, file_name)
                if os.path.exists(received_file_path):
                    file_metadata = {
                        "path": [f"peer{peer_id}", file_name],
                        "length": os.path.getsize(received_file_path)
                    }
                    if file_metadata not in torrent_data["info"]["files"]:
                        torrent_data["info"]["files"].append(file_metadata)

            # Save updated data
            with open(torrent_path, 'w') as torrent_file:
                json.dump(torrent_data, torrent_file, indent=4)

            print(f"Torrent.json updated successfully for peer {peer_id}.")
    except Exception as e:
        print(f"Error updating torrent.json: {e}")

# Old
# def download_file_concurrently(peer_id, file_name, pieces_to_peers, chunk_size):
#     """
#     Download multiple file pieces from peers concurrently.

#     Args:
#         peer_id (str): ID of the current peer. Used to manage folder paths and identify the peer.
#         file_name (str): Name of the file being downloaded.
#         pieces_to_peers (dict): A dictionary where keys are piece hashes, and values are lists of peer information 
#                                 (e.g., IP and port) that have the respective piece.
#         chunk_size (int): Size of each chunk in bytes. This determines how large each downloaded piece will be.

#     Raises:
#         ValueError: If a downloaded piece fails validation after combining all pieces.
#     """
#     # Create a folder to store the downloaded chunks if it does not already exist
#     chunk_folder = f"peer{peer_id}/chunks"
#     os.makedirs(chunk_folder, exist_ok=True)

#     # Initialize a list to keep track of threads created for downloading pieces
#     threads = []
#     # Create a list of piece hashes to maintain the correct order of pieces during the combination phase
#     piece_order = list(pieces_to_peers.keys())

#     # Iterate through each piece hash and its associated peers
#     for chunk_index, (piece_hash, peers) in enumerate(pieces_to_peers.items()):
#         # Skip downloading this piece if it is already in the download tracker
#         if piece_hash in download_tracker:
#             print(f"Skipping already downloaded piece: {piece_hash}")
#             continue

#         # Select a peer for the current piece using a round-robin strategy
#         # The round-robin strategy ensures a balanced load distribution across peers
#         selected_peer = peers[chunk_index % len(peers)]
#         peer_host = selected_peer["ip"]  # IP address of the selected peer
#         peer_port = selected_peer["port"]  # Port of the selected peer

#         # Define the file path where the chunk will be saved locally
#         output_path = os.path.join(chunk_folder, f"{piece_hash}.chunk")

#         # Create a thread for downloading the piece from the selected peer
#         thread = threading.Thread(
#             target=download_piece_from_peer,
#             args=(
#                 peer_host,          # IP of the peer providing the piece
#                 peer_port,          # Port of the peer providing the piece
#                 piece_hash,         # Hash of the piece to be downloaded
#                 output_path,        # Local path where the piece will be saved
#                 peers[1:],          # Remaining peers to use in case of failure
#                 peer_id,            # Current peer ID
#                 file_name,          # File name being downloaded
#                 chunk_index         # Index of the chunk for validation purposes
#             )
#         )

#         # Add the thread to the list of threads
#         threads.append(thread)
#         # Add the piece hash to the download tracker to avoid duplicate downloads
#         download_tracker.add(piece_hash)
#         # Start the thread for concurrent downloading
#         thread.start()

#     # Wait for all threads to complete downloading
#     for thread in threads:
#         thread.join()

#     print("All pieces downloaded. Combining...")
#     # Combine all the downloaded pieces into the final file and validate its integrity
#     combine_and_validate_pieces(
#         chunk_folder,                              # Folder containing the downloaded pieces
#         f"peer{peer_id}/received_files/{file_name}",  # Final output path for the combined file
#         piece_order                               # Order in which the pieces should be combined
#     )

# New
def download_file_concurrently(peer_id, file_name, pieces_to_peers, chunk_size):
    """
    Download multiple file pieces from peers concurrently.
    """
    chunk_folder = f"peer{peer_id}/chunks"
    os.makedirs(chunk_folder, exist_ok=True)

    threads = []
    piece_order = list(pieces_to_peers.keys())

    for chunk_index, (piece_hash, peers) in enumerate(pieces_to_peers.items()):
        if piece_hash in download_tracker:
            continue

        selected_peer = peers[chunk_index % len(peers)]
        peer_host = selected_peer["ip"]
        peer_port = selected_peer["port"]
        output_path = os.path.join(chunk_folder, f"{piece_hash}.chunk")

        thread = threading.Thread(
            target=download_piece_from_peer,
            args=(peer_host, peer_port, piece_hash, output_path, peers[1:], peer_id, file_name, chunk_index)
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    print("All pieces downloaded. Combining...")
    combine_and_validate_pieces(chunk_folder, f"peer{peer_id}/received_files/{file_name}", piece_order)

def request_pieces_info(tracker_host, tracker_port, file_name):
    """
    Request information about pieces and their associated peers from the tracker.

    Args:
        tracker_host (str): The tracker server's IP address.
        tracker_port (int): The tracker server's port number.
        file_name (str): The name of the file for which piece info is requested.

    Returns:
        dict: Mapping of piece hashes to lists of peer information.

    Raises:
        Exception: If there is an error communicating with the tracker.
    """
    # Old
    # try:
    #     with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    #         s.connect((tracker_host, tracker_port))
    #         request_message = f"PIECE_INFO_REQUEST|{file_name}"
    #         s.sendall(request_message.encode('utf-8'))
            
    #         response = s.recv(4096)
    #         pieces_to_peers = json.loads(response.decode('utf-8'))
    #         print(f"Received pieces-to-peers mapping: {pieces_to_peers}")
    #         return pieces_to_peers
    # except Exception as e:
    #     print(f"Error requesting piece info: {e}")
    #     return {}
    # New
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            request_message = f"PIECE_INFO_REQUEST|{file_name}"
            s.sendall(request_message.encode('utf-8'))

            # Read the data length header
            header = s.recv(1024).decode('utf-8')
            if not header.startswith("DATA_LENGTH|"):
                print("[ERROR] Invalid response header from tracker")
                return {}
            data_length = int(header.split('|')[1])
            print(f"Expecting {data_length} bytes of piece info data")

            # Receive the full JSON data in chunks
            received_data = b""
            while len(received_data) < data_length:
                chunk = s.recv(4096)
                if not chunk:
                    print("[ERROR] Connection closed before receiving all data")
                    break
                received_data += chunk

            # Parse the JSON response
            if len(received_data) == data_length:
                pieces_to_peers = json.loads(received_data.decode('utf-8'))
                print(f"Received pieces-to-peers mapping: {pieces_to_peers}")
                return pieces_to_peers
            else:
                print("[ERROR] Received data size mismatch")
                return {}
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON decoding error: {e}")
        return {}
    except Exception as e:
        print(f"[ERROR] Error requesting piece info: {e}")
        return {}

def compute_info_hash(info):
    """
    Compute the SHA-1 hash of the `info` dictionary.

    Args:
        info (dict): The info dictionary to hash.

    Returns:
        str: The computed SHA-1 hash.
    """
    info_str = json.dumps(info, sort_keys=True).encode('utf-8')
    return hashlib.sha1(info_str).hexdigest()

def update_torrent_json(peer_id, file_path, chunk_size):
    """
    Update the torrent.json file with metadata of a newly uploaded file.

    Args:
        peer_id (str): ID of the peer.
        file_path (str): Path to the uploaded file.
        chunk_size (int): Size of each chunk in bytes.

    Returns:
        dict: Updated info section of the torrent file, or None if an error occurs.

    Raises:
        Exception: If an error occurs during file processing or updating the torrent.json file.
    """
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
        updated_pieces = []
        with open(file_path, 'rb') as f:
            chunk_index = 0
            while chunk := f.read(chunk_size):
                # Old
                # piece_hash = compute_chunk_hash(chunk, chunk_index)
                # New 
                piece_hash = compute_chunk_hash_3(chunk, chunk_index, file_name)
                updated_pieces.append({"piece": piece_hash, 
                                       "file_path": f"peer{peer_id}",
                                       "file_name": f"{file_name}",
                                       "index": chunk_index})

                # Save the chunk to the chunks folder
                chunk_file_path = os.path.join(chunks_folder, f"{piece_hash}.chunk")
                with open(chunk_file_path, 'wb') as chunk_file:
                    chunk_file.write(chunk)
                # print(f"Stored chunk: {chunk_file_path} with hash {piece_hash}")
                chunk_index += 1

        # Update the pieces array
        if "pieces" in torrent_data["info"]:
            torrent_data["info"]["pieces"].extend(updated_pieces)
        else:
            torrent_data["info"]["pieces"] = updated_pieces

        # Save the updated torrent.json
        with open(torrent_path, 'w') as torrent_file:
            json.dump(torrent_data, torrent_file, indent=4)

        # Compute new info_hash
        new_info_hash = compute_info_hash(torrent_data["info"])
        print(f"Computed new info_hash: {new_info_hash}")

        return torrent_data["info"]
    except Exception as e:
        print(f"Error updating torrent.json: {e}")
        return None

def update_torrent_transfer_pieces(peer_id, file_name, file_size, chunk_path, chunk_size):
    """
    Update the torrent.json file after receiving file pieces.

    This function updates the torrent metadata (torrent.json) for a peer by 
    including metadata about received file pieces and the complete file. 
    It ensures that the received chunks are recorded properly, and the 
    torrent.json structure is updated with any new data.

    Args:
        peer_id (str): The ID of the peer receiving the pieces.
        file_name (str): The name of the file being reconstructed.
        file_size (int): The total size of the file in bytes.
        chunk_path (str): The directory path where the received chunks are stored.
        chunk_size (int): The size of each chunk in bytes.

    Returns:
        dict: The updated "info" section of the torrent.json file.
        None: If any error occurs during the process.

    Raises:
        Exception: If an error occurs during file or chunk processing.

    Notes:
        - The function validates the existence of the torrent.json file and chunk directory.
        - It ensures that duplicate file or piece entries are not added to torrent.json.
        - File metadata includes the file path and size, and chunk metadata includes 
          SHA-1 hash values to uniquely identify each chunk.
    """
    try:
        # Define the torrent file path
        torrent_path = f"peer{peer_id}/torrent.json"

        # Ensure the file and chunk directory exist
        if not os.path.exists(torrent_path):
            print(f"Error: {torrent_path} not found.")
            return None
        if not os.path.isdir(chunk_path):
            print(f"Error: Chunk path {chunk_path} is not a directory.")
            return None

        # Load the current torrent.json content
        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)

        # Check for existing pieces and files in torrent.json
        existing_pieces = {piece["piece"] for piece in torrent_data["info"]["pieces"]}
        existing_files = {tuple(file_info["path"]) for file_info in torrent_data["info"]["files"]}

        # Add file metadata if not present
        file_key = (f"peer{peer_id}", file_name)
        if file_key not in existing_files:
            file_metadata = {
                "path": [f"peer{peer_id}", file_name],
                "length": file_size
            }
            torrent_data["info"]["files"].append(file_metadata)
            print(f"Added file metadata: {file_metadata}")

        # Read chunks and update pieces
        updated_pieces = []
        for chunk_file in sorted(os.listdir(chunk_path)):  # Ensure chunks are in order
            chunk_file_path = os.path.join(chunk_path, chunk_file)
            if os.path.isfile(chunk_file_path):
                with open(chunk_file_path, 'rb') as chunk:
                    chunk_data = chunk.read()
                    piece_hash = hashlib.sha1(chunk_data).hexdigest()
                    if piece_hash not in existing_pieces:
                        updated_pieces.append({"piece": piece_hash})
                        print(f"Added piece hash from {chunk_file}: {piece_hash}")
            else:
                print(f"Skipping non-file entry in chunks: {chunk_file}")

        # Update the pieces list
        torrent_data["info"]["pieces"].extend(updated_pieces)

        # Save the updated torrent.json
        with open(torrent_path, 'w') as torrent_file:
            json.dump(torrent_data, torrent_file, indent=4)
            print(f"Updated torrent.json successfully for peer {peer_id}.")

        return torrent_data["info"]
    except Exception as e:
        print(f"Error updating torrent.json from pieces: {e}")
        return None

def split_file(file_path, chunk_size):
    """
    Split a file into smaller chunks.

    Args:
        file_path (str): Path to the file to be split.
        chunk_size (int): Size of each chunk in bytes.

    Raises:
        FileNotFoundError: If the input file is not found.
        Exception: For other errors during file splitting.
    """
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

def combine_files(part_files, output_file):
    """
    Combine smaller chunks into the original file.

    Args:
        part_files (list): List of paths to the chunk files.
        output_file (str): Path to save the combined file.

    Raises:
        FileNotFoundError: If one or more part files are not found.
        Exception: For other errors during file combining.
    """
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

def upload_file(peer_id, file_path, chunk_size=1024):
    """
    Upload a file by splitting it into chunks and storing locally.

    Args:
        peer_id (str): ID of the current peer.
        file_path (str): Path to the file to upload.
        chunk_size (int, optional): Size of each chunk in bytes. Defaults to 1024.

    Raises:
        Exception: For errors during file upload or chunk storage.
    """
    try:
        chunks_folder = f"peer{peer_id}/chunks"
        os.makedirs(chunks_folder, exist_ok=True)

        file_name = os.path.basename(file_path)
        piece_order = []

        with open(file_path, 'rb') as f:
            chunk_index = 0  # Start with the first chunk index
            while chunk := f.read(chunk_size):
                # Compute a unique hash for each chunk
                # Old
                # piece_hash = compute_chunk_hash(chunk, chunk_index)
                # New
                piece_hash = compute_chunk_hash_3(chunk, chunk_index, file_name)
                part_file_name = os.path.join(chunks_folder, f"{piece_hash}.chunk")
                with open(part_file_name, 'wb') as part_file:
                    part_file.write(chunk)
                piece_order.append(piece_hash)
                # print(f"Stored chunk: {part_file_name} with hash {piece_hash}")
                chunk_index += 1  # Increment the chunk index

        # print(f"Piece order: {piece_order}")
    except Exception as e:
        print(f"Error uploading file: {e}")
        
def validate_chunk(chunk_data, chunk_index, file_name, expected_hash):
    """
    Validate a chunk against its expected hash.

    Args:
        chunk_data (bytes): Data of the chunk.
        chunk_index (int): Index of the chunk.
        expected_hash (str): Expected hash of the chunk.

    Returns:
        bool: True if the chunk is valid, False otherwise.
    """
    actual_hash = compute_chunk_hash_3(chunk_data, chunk_index, file_name)
    return actual_hash == expected_hash

def combine_and_validate_pieces(received_folder, output_file, piece_order):
    """
    Combine pieces into a file and validate its integrity.

    Args:
        received_folder (str): Folder containing the received pieces.
        output_file (str): Path to save the combined file.
        piece_order (list): List of piece hashes in the correct order.

    Raises:
        Exception: If there are errors during file combining or validation.
    """
    try:
        file_name = os.path.basename(output_file)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with file_lock:
            with open(output_file, 'wb') as output:
                for chunk_index, piece_hash in enumerate(piece_order):
                    piece_path = os.path.join(received_folder, f"{piece_hash}.chunk")
                    if os.path.exists(piece_path):
                        with open(piece_path, 'rb') as pf:
                            content = pf.read()
                            if not validate_chunk(content, chunk_index, file_name, piece_hash):
                                print(f"Error: Piece {piece_hash} did not pass validation!")
                                continue
                            output.write(content)
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

def notify_tracker_of_update(peer_id, file_name, chunk_size):
    """
    Notify the tracker of updates to the torrent.json file.

    Args:
        peer_id (str): ID of the current peer.
        file_name (str): Name of the updated file.

    Raises:
        Exception: If there are errors communicating with the tracker.
    """
    try:
        torrent_path = f"peer{peer_id}/torrent.json"
        chunks_path = f"peer{peer_id}/chunks"
        if not os.path.exists(torrent_path):
            print(f"Error: Torrent file {torrent_path} not found.")
            return
        if not os.path.exists(chunks_path):
            print(f"Error: Chunk path {chunks_path} not found.")
            return
        # Load the current torrent.json content
        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)
        # Ensure 'pieces' exists in the JSON structure
        if "info" not in torrent_data or "pieces" not in torrent_data["info"]:
            print(f"Error: Invalid torrent.json structure in {torrent_path}.")
            return
        # Read all chunks and compute their hashes
        updated_pieces = []
        for chunk_file in sorted(os.listdir(chunks_path)):  # Ensure proper order
            chunk_file_path = os.path.join(chunks_path, chunk_file)
            if os.path.isfile(chunk_file_path):  # Ensure it's a file
                with open(chunk_file_path, 'rb') as chunk:
                    chunk_data = chunk.read()
                    piece_hash = hashlib.sha1(chunk_data).hexdigest()
                    updated_pieces.append({"piece": piece_hash})
                    # print(f"Computed hash for chunk {chunk_file}: {piece_hash}")
            else:
                print(f"Skipping non-file entry in chunks: {chunk_file}")

        # Update the pieces list in torrent.json
        torrent_data["info"]["pieces"] = updated_pieces
        # print(f"Updated pieces: {updated_pieces}")
        
        # Load the updated torrent.json
        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)

        # Extract info section
        info_data = json.dumps(torrent_data["info"])
        info_length = len(info_data)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))

            # Send header with info length
            header = f"UPDATE_PEER|{peer_id}|{info_length}|".encode('utf-8')
            s.sendall(header)

            # Send the info data in chunks
            for i in range(0, info_length, chunk_size):
                s.sendall(info_data[i:i + chunk_size].encode('utf-8'))

            # Wait for acknowledgment
            response = s.recv(1024).decode('utf-8')
            print(f"Tracker response: {response}")
    except Exception as e:
        print(f"Error notifying tracker: {e}")

def handle_peer_connection(conn, peer_id):
    """
    Handle incoming connections from other peers.

    Args:
        conn (socket): The connection object.
        peer_id (str): ID of the current peer.

    Raises:
        Exception: If there are errors during communication or processing.
    """
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
        if data.startswith("PIECE_TRANSFER"):
            _, file_name, file_size, chunk_size, total_pieces = data.split('|')
            chunk_size = int(chunk_size)
            total_pieces = int(total_pieces)
            received_folder = f"peer{peer_id}/chunks"
            os.makedirs(received_folder, exist_ok=True)
            conn.sendall("READY".encode('utf-8'))

            for _ in range(total_pieces):
                piece_metadata = conn.recv(1024).decode('utf-8')
                if piece_metadata.startswith("PIECE"):
                    _, piece_name, expected_hash = piece_metadata.split('|')
                    piece_path = os.path.join(received_folder, piece_name)
                    with open(piece_path, 'wb') as piece_file:
                        piece_data = conn.recv(chunk_size)
                        piece_file.write(piece_data)
                        actual_hash = hashlib.sha1(piece_data).hexdigest()
                        if actual_hash == expected_hash:
                            conn.sendall("RECEIVED".encode('utf-8'))
                        else:
                            conn.sendall("HASH_MISMATCH".encode('utf-8'))
                            return

            # Update torrent.json with received pieces
            updated_info = update_torrent_transfer_pieces(peer_id, file_name, int(file_size), received_folder, chunk_size)

            # Notify tracker if update is successful
            if updated_info:
                notify_tracker_of_update(peer_id, file_name, chunk_size)

            # Combine pieces and validate
            print(f"All pieces of {file_name} received successfully. Validating...")
            combine_and_validate_pieces(received_folder, f"peer{peer_id}/received_files/{file_name}")
            conn.sendall("TRANSFER_COMPLETE".encode('utf-8'))
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

# Old
# def start_upload_server(peer_id, upload_port):
#     """
#     Starts a server for handling upload requests.
#     Each connection is handled in a separate thread.
#     """
#     try:
#         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as upload_socket:
#             upload_socket.bind(('0.0.0.0', upload_port))
#             upload_socket.listen()
#             print(f"Upload server running for peer {peer_id} on port {upload_port}")

#             while True:
#                 conn, addr = upload_socket.accept()
#                 threading.Thread(target=handle_peer_connection, args=(conn, peer_id)).start()
#     except Exception as e:
#         print(f"[ERROR] Upload server error for peer {peer_id}: {e}")

# New
def start_upload_server(peer_id, upload_port):
    """
    Starts a server for handling upload requests.
    Each connection is handled in a separate thread.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as upload_socket:
            upload_socket.bind(('0.0.0.0', upload_port))
            upload_socket.listen()
            print(f"Upload server running for peer {peer_id} on port {upload_port}")

            while True:
                conn, addr = upload_socket.accept()
                thread = threading.Thread(target=handle_peer_connection, args=(conn, peer_id), daemon=True)
                thread.start()
    except Exception as e:
        print(f"[ERROR] Upload server error for peer {peer_id}: {e}")


def peer_server(port, peer_id):
    """
    Start a peer server to handle incoming connections.

    Args:
        port (int): Port number for the peer server.
        peer_id (str): ID of the current peer.

    Raises:
        Exception: If there are errors setting up the server.
    """
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

def connect_to_peer(peer_host, peer_port, message):
    """
    Connect to another peer and send a message.

    Args:
        peer_host (str): IP address of the peer.
        peer_port (int): Port number of the peer.
        message (str): Message to send.

    Raises:
        Exception: If there are errors during connection or message delivery.
    """
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

def register_with_tracker(tracker_host, tracker_port, peer_id, peer_port, info_hash):
    """
    Register the peer with the tracker.

    Args:
        tracker_host (str): IP address of the tracker.
        tracker_port (int): Port number of the tracker.
        peer_id (str): ID of the current peer.
        peer_port (int): Port number of the current peer.
        info_hash (str): Info hash of the peer's torrent data.

    Returns:
        str: Hostname of the tracker, or None if registration fails.

    Raises:
        Exception: If there are errors during registration.
    """
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

def deregister_from_tracker(tracker_host, tracker_port, peer_id):
    """
    Deregister the peer from the tracker.

    Args:
        tracker_host (str): IP address of the tracker.
        tracker_port (int): Port number of the tracker.
        peer_id (str): ID of the current peer.

    Raises:
        Exception: If there are errors during deregistration.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"DISCONNECT|{peer_id}".encode('utf-8'))
            response = s.recv(1024)
            print(response.decode('utf-8'))
    except Exception as e:
        print(f"Error while deregistering: {e}")

def request_peers_list(tracker_host, tracker_port, peer_id):
    """
    Request a list of peers from the tracker.

    Args:
        tracker_host (str): IP address of the tracker.
        tracker_port (int): Port number of the tracker.
        peer_id (str): ID of the current peer.

    Returns:
        list: A list of peers.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            s.sendall(f"LISTREQUEST|{peer_id}".encode('utf-8'))

            # Receive the data length first
            header = s.recv(1024).decode('utf-8')
            if not header.startswith("DATA_LENGTH|"):
                print("[ERROR] Invalid response header from tracker")
                return []
            data_length = int(header.split('|')[1])
            print(f"Expecting {data_length} bytes of peer list data")

            # Receive the full data in chunks
            received_data = b""
            while len(received_data) < data_length:
                chunk = s.recv(4096)
                if not chunk:  # Connection closed prematurely
                    print("[ERROR] Connection closed before receiving all data")
                    break
                received_data += chunk

            if len(received_data) != data_length:
                print("[ERROR] Received data size mismatch")
                return []

            # Parse the JSON response
            peers = json.loads(received_data.decode('utf-8'))
            # Old
            # print(f"Received peer list: {peers}")
            # return peers
            # New
            return "Receiving peer list here"
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON decoding error: {e}")
        print(f"Partial data received: {received_data.decode('utf-8')}")
    except Exception as e:
        print(f"[ERROR] Error while requesting peer list: {e}")
    return []

def send_file_pieces_to_peer(peer_host, peer_port, peer_id, file_name, chunk_size):
    """
    Send file pieces to another peer.

    Args:
        peer_host (str): IP address of the receiving peer.
        peer_port (int): Port number of the receiving peer.
        peer_id (str): ID of the current peer.
        file_name (str): Name of the file being sent.
        chunk_size (int): Size of each chunk in bytes.

    Raises:
        Exception: If there are errors during file piece transfer.
    """
    try:
        file_path = f"peer{peer_id}/chunks"
        # Define the torrent file path
        file_info = f"peer{peer_id}/torrent.json"

        # Ensure the file exists
        if not os.path.exists(file_info):
            print(f"Error: {file_info} not found.")
            return None

        # Load the current torrent.json content
        with open(file_info, 'r') as file:
            file_data = json.load(file)
        for file_info in file_data["info"]["files"]:
            if file_info["path"][-1] == file_name:  # Match the last part of the path
                file_size = file_info["length"]
        pieces = os.listdir(file_path)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_host, peer_port))
            # Send metadata to the receiver
            metadata_message = f"PIECE_TRANSFER|{file_name}|{file_size}|{chunk_size}|{len(pieces)}"
            s.sendall(metadata_message.encode('utf-8'))

            response = s.recv(1024).decode('utf-8')
            if response != "READY":
                print(f"Peer not ready for piece transfer: {response}")
                return

            for piece_name in pieces:
                piece_path = os.path.join(file_path, piece_name)
                with open(piece_path, 'rb') as piece_file:
                    piece_data = piece_file.read()
                    piece_hash = hashlib.sha1(piece_data).hexdigest()
                    piece_message = f"PIECE|{piece_name}|{piece_hash}"
                    s.sendall(piece_message.encode('utf-8'))
                    time.sleep(0.1)  # Wait for receiver to prepare
                    s.sendall(piece_data)
                    response = s.recv(1024).decode('utf-8')
                    if response != "RECEIVED":
                        print(f"Error transferring piece {piece_name}: {response}")
                        return
            print("All pieces sent successfully.")
    except Exception as e:
        print(f"Error sending file pieces: {e}")

def shutdown_gracefully(signal, frame):
    """
    Handle graceful shutdown of the peer server.

    Args:
        signal (int): The signal number.
        frame: The current stack frame.

    Raises:
        SystemExit: To exit the program cleanly.
    """
    print("\n[INFO] Shutting down the peer server...")
    sys.exit(0)

def initialize_peer_directory(peer_id, piece_length):
    """
    Initialize the directory and torrent.json for a peer.

    Args:
        peer_id (str): ID of the peer.
        piece_length (int): Length of each piece in bytes.

    Raises:
        Exception: If there's an error during initialization.
    """
    try:
        peer_directory = f"peer{peer_id}"
        torrent_file_path = os.path.join(peer_directory, "torrent.json")

        # Create the peer directory if it doesn't exist
        os.makedirs(peer_directory, exist_ok=True)

        # Check if torrent.json already exists
        if not os.path.exists(torrent_file_path):
            # Create the initial torrent.json structure
            torrent_data = {
                "announce": "0.0.0.0:4000",
                "info": {
                    "name": str(peer_id),
                    "piece length": piece_length,  # Ensure this is an integer
                    "pieces": [],
                    "files": []
                },
                "announce list": []
            }

            # Write the JSON structure to the file
            with open(torrent_file_path, "w") as torrent_file:
                json.dump(torrent_data, torrent_file, indent=4)

            print(f"Initialized {torrent_file_path} for peer {peer_id}")
        else:
            print(f"{torrent_file_path} already exists for peer {peer_id}")
    except Exception as e:
        print(f"Error initializing peer directory: {e}")

# OLD
# if __name__ == "__main__":
#     peer_id = sys.argv[1]
#     peer_port = int(sys.argv[2])
#     # Configuration
#     file = open(f'peer{peer_id}/torrent.json')
#     peer_data = json.load(file)
#     info = peer_data["info"]
#     chunk_size = info["piece length"]
#     info_hash = json.dumps(info, indent=4)  # We get the info as a string first, hash will be implemented later
#     # Setup signal handling in the main thread
#     signal.signal(signal.SIGINT, shutdown_gracefully)

#     # Start peer server
#     threading.Thread(target=peer_server, args=(peer_port,peer_id), daemon=True).start()

#     # Register with tracker
#     peer_host = register_with_tracker(tracker_host, tracker_port, peer_id, peer_port, info_hash)

#     try:
#         while True:
#             # Listen for user commands
#             print("Enter a command (CONNECT <peer_host> <peer_port> or SEND <peer_host> <peer_port> <file_name> or UPLOAD <file_path> or EXIT):")
#             command = input().strip()
#             if command.startswith("CONNECT"):
#                 _, peer_host, peer_port = command.split()
#                 peer_port = int(peer_port)
#                 message = f"Hello from peer {peer_id}!"
#                 connect_to_peer(peer_host, peer_port, message)
#             if command.startswith("SEND"):
#                 _, peer_host, peer_port, file_name = command.split()
#                 peer_port = int(peer_port)
#                 send_file_pieces_to_peer(peer_host, peer_port, peer_id, file_name, chunk_size)
#             if command.startswith("UPLOAD"):
#                 _, file_path = command.split()
#                 if os.path.exists(file_path):
#                     print(f"Uploading file: {file_path}...")
#                     # Use the upload_file function to split and store locally
#                     upload_file(peer_id, file_path, chunk_size)
#                     # Update the torrent.json and compute the new info_hash
#                     new_info_hash = update_torrent_json(peer_id, file_path, chunk_size)
#                     if new_info_hash:
#                     # Notify the tracker about the updated info_hash
#                         try:
#                             with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#                                 s.connect((tracker_host, tracker_port))
#                                 print(f"Update peer hereee: {peer_id}")
#                                 update_message = f"UPDATE_PEER|{peer_id}|{json.dumps(new_info_hash)}"
#                                 s.sendall(update_message.encode('utf-8'))
#                                 response = s.recv(1024).decode('utf-8')
#                                 print(f"Tracker response: {response}")
#                         except Exception as e:
#                             print(f"Error notifying tracker: {e}")
#                             print("File upload complete.")
#                     else:
#                         print(f"Error: File {file_path} does not exist.")
#             if command.startswith("DOWNLOAD"):
#                 _, file_name = command.split()
#                 pieces_to_peers = request_pieces_info(tracker_host, tracker_port, file_name)
#                 if pieces_to_peers:
#                     download_file_concurrently(peer_id, file_name, pieces_to_peers, chunk_size)

#                     # Added for test
#                     # Load the current torrent.json content
#                     temp_torrent_path = f'peer{peer_id}/torrent.json'
#                     with open(temp_torrent_path, 'r') as torrent_file:
#                         temp_torrent_data = json.load(torrent_file)
#                     new_info_hash = temp_torrent_data["info"]
#                     try:
#                         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#                             s.connect((tracker_host, tracker_port))
#                             print(f"Update peer hereee: {peer_id}")
#                             update_message = f"UPDATE_PEER|{peer_id}|{json.dumps(new_info_hash)}"
#                             s.sendall(update_message.encode('utf-8'))
#                             response = s.recv(1024).decode('utf-8')
#                             print(f"Tracker response: {response}")
#                     except Exception as e:
#                         print(f"Error notifying tracker: {e}")
#                         print("File upload complete.")
#                     # End add for test
#                 else:
#                     print("No piece info available for download.")
#             elif command == "EXIT":
#                 print("Exiting...")
#                 deregister_from_tracker(tracker_host, tracker_port, peer_id)
#                 break
#             request_peers_list(tracker_host, tracker_port, peer_id)
#     except KeyboardInterrupt:
#         deregister_from_tracker(tracker_host, tracker_port, peer_id)

# NEW 1
# Main script logic
if __name__ == "__main__":
    # Fetch the peer ID and port from command-line arguments
    peer_id = sys.argv[1]
    peer_port = int(sys.argv[2])
    piece_length = 5  # Define the piece length (e.g., 5 bytes)

    # Initialize the peer directory and torrent.json
    initialize_peer_directory(peer_id=peer_id, piece_length=piece_length)
    
    # Configuration
    file = open(f'peer{peer_id}/torrent.json')
    peer_data = json.load(file)
    info = peer_data["info"]
    chunk_size = info["piece length"]
    info_hash = json.dumps(info, indent=4)  # We get the info as a string first, hash will be implemented later
    
    # Setup signal handling in the main thread
    signal.signal(signal.SIGINT, shutdown_gracefully)
    
    # added
    # Start Peer Server for uploads
    # upload_port = peer_port + 1  # Use a different port for the upload server
    # threading.Thread(target=start_upload_server, args=(peer_id, upload_port), daemon=True).start()
    # end

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
            
            if command.startswith("SEND"):
                _, peer_host, peer_port, file_name = command.split()
                peer_port = int(peer_port)
                send_file_pieces_to_peer(peer_host, peer_port, peer_id, file_name, chunk_size)
            
            if command.startswith("UPLOAD"):
                _, file_path = command.split()
                if os.path.exists(file_path):
                    print(f"Uploading file: {file_path}...")

                    # Use the upload_file function to split and store locally
                    upload_file(peer_id, file_path, chunk_size)
                    
                    # Update the torrent.json and compute the new info_hash
                    new_info_hash = update_torrent_json(peer_id, file_path, chunk_size)
                    if new_info_hash:
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.connect((tracker_host, tracker_port))
                                print(f"Notifying tracker about upload for peer {peer_id}...")

                                # Serialize the new_info_hash as a string
                                new_info_hash_str = json.dumps(new_info_hash)
                                info_hash_length = len(new_info_hash_str)

                                # Send the header with metadata length
                                header = f"UPDATE_PEER|{peer_id}|{info_hash_length}|".encode('utf-8')
                                s.sendall(header)

                                # Send the metadata in chunks
                                # chunk_size = 4096
                                for i in range(0, info_hash_length, chunk_size):
                                    s.sendall(new_info_hash_str[i:i + chunk_size].encode('utf-8'))

                                # Receive acknowledgment from the tracker
                                response = s.recv(1024).decode('utf-8')
                                print(f"Tracker response: {response}")
                        except Exception as e:
                            print(f"Error notifying tracker: {e}")
                    else:
                        print(f"Error: File {file_path} does not exist.")

            if command.startswith("DOWNLOAD"):
                _, file_name = command.split()
                pieces_to_peers = request_pieces_info(tracker_host, tracker_port, file_name)
                if pieces_to_peers:
                    download_file_concurrently(peer_id, file_name, pieces_to_peers, chunk_size)
                    
                    # Prepare updated `info_hash`
                    torrent_path = f'peer{peer_id}/torrent.json'
                    with open(torrent_path, 'r') as torrent_file:
                        torrent_data = json.load(torrent_file)

                    # Add `file_name`, `file_path`, and `index` to pieces
                    for piece_index, piece in enumerate(torrent_data["info"]["pieces"]):
                        piece["file_name"] = file_name
                        piece["file_path"] = f"peer{peer_id}"
                        piece["index"] = piece_index

                    # Save the updated torrent.json
                    with open(torrent_path, 'w') as torrent_file:
                        json.dump(torrent_data, torrent_file, indent=4)

                    # Notify the tracker with the updated `info_hash`
                    new_info_hash = torrent_data["info"]
                    
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect((tracker_host, tracker_port))
                            print(f"Notifying tracker about updated peer info for peer {peer_id}...")
                            
                            # Serialize the `info_hash` into a JSON string
                            new_info_hash_str = json.dumps(new_info_hash)
                            info_hash_length = len(new_info_hash_str)
                            
                            # Send the header with the length of the `info_hash`
                            header = f"UPDATE_PEER|{peer_id}|{info_hash_length}|".encode('utf-8')
                            s.sendall(header)
                            
                            # Send the `info_hash` data in chunks
                            for i in range(0, info_hash_length, chunk_size):
                                s.sendall(new_info_hash_str[i:i + chunk_size].encode('utf-8'))
                            
                            # Wait for acknowledgment from the tracker
                            response = s.recv(1024).decode('utf-8')
                            print(f"Tracker response: {response}")
                    except Exception as e:
                        print(f"Error notifying tracker: {e}")
                    # End add for test
                else:
                    print("No piece info available for download.")
            
            elif command == "EXIT":
                print("Exiting...")
                deregister_from_tracker(tracker_host, tracker_port, peer_id)
                break
            request_peers_list(tracker_host, tracker_port, peer_id)
    except KeyboardInterrupt:
        deregister_from_tracker(tracker_host, tracker_port, peer_id)
        
# New 2
# if __name__ == "__main__":
#     peer_id = sys.argv[1]
#     peer_port = int(sys.argv[2])
#     piece_length = 5  # Define the piece length (e.g., 5 bytes)

#     # Initialize the peer directory and torrent.json
#     initialize_peer_directory(peer_id=peer_id, piece_length=piece_length)

#     # Configuration
#     with open(f'peer{peer_id}/torrent.json', 'r') as file:
#         peer_data = json.load(file)
#     info = peer_data["info"]
#     chunk_size = info["piece length"]
#     info_hash = json.dumps(info, indent=4)

#     # Setup signal handling
#     signal.signal(signal.SIGINT, shutdown_gracefully)

#     # Start Peer Server for uploads
#     upload_port = peer_port + 1  # Use a different port for the upload server
#     threading.Thread(target=start_upload_server, args=(peer_id, upload_port), daemon=True).start()

#     # Register with tracker
#     peer_host = register_with_tracker(tracker_host, tracker_port, peer_id, peer_port, info_hash)

#     # Main Command Loop
#     try:
#         while True:
#             print("Enter a command (CONNECT <peer_host> <peer_port>, SEND, UPLOAD, DOWNLOAD, or EXIT):")
#             command = input().strip()
            
#             if command.startswith("CONNECT"):
#                 _, peer_host, peer_port = command.split()
#                 peer_port = int(peer_port)
#                 message = f"Hello from peer {peer_id}!"
#                 connect_to_peer(peer_host, peer_port, message)
            
#             elif command.startswith("SEND"):
#                 _, peer_host, peer_port, file_name = command.split()
#                 peer_port = int(peer_port)
#                 send_file_pieces_to_peer(peer_host, peer_port, peer_id, file_name, chunk_size)
            
#             elif command.startswith("UPLOAD"):
#                 _, file_path = command.split()
#                 if os.path.exists(file_path):
#                     upload_file(peer_id, file_path, chunk_size)
#                     new_info_hash = update_torrent_json(peer_id, file_path, chunk_size)
#                     if new_info_hash:
#                         notify_tracker_of_update(peer_id, file_path, chunk_size)
            
#             elif command.startswith("DOWNLOAD"):
#                 _, file_name = command.split()
#                 pieces_to_peers = request_pieces_info(tracker_host, tracker_port, file_name)
#                 if pieces_to_peers:
#                     threading.Thread(
#                         target=download_file_concurrently,
#                         args=(peer_id, file_name, pieces_to_peers, chunk_size),
#                         daemon=True
#                     ).start()
#                 else:
#                     print("No piece info available for download.")
            
#             elif command == "EXIT":
#                 print("Exiting...")
#                 deregister_from_tracker(tracker_host, tracker_port, peer_id)
#                 break
#     except KeyboardInterrupt:
#         deregister_from_tracker(tracker_host, tracker_port, peer_id)
     

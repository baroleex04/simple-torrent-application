import socket
import sys
import json
import os
import time
import random
import threading
import signal
import hashlib
import logging
from datetime import datetime

# Add logger initialization before any other code
def setup_logger(peer_id):
    """Initialize logger for the peer."""
    logger = logging.getLogger(f'peer{peer_id}')
    logger.setLevel(logging.INFO)
    
    # Create peer directory if it doesn't exist
    os.makedirs(f"peer{peer_id}", exist_ok=True)
    
    # Create file handler
    fh = logging.FileHandler(f'peer{peer_id}/peer{peer_id}.log')
    fh.setLevel(logging.INFO)
    
    # Create console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.connect(("8.8.8.8", 80))
    tracker_host = s.getsockname()[0]

# tracker_host = '192.168.68.52'
tracker_port = 4000
download_tracker = set()

INSTRUCTION = """
INSTRUCTION
DOWNLOAD <file_name>: Download a file from peers.
UPLOAD <file_name>: Upload a file to server.
EXIT: Disconnect with the server.
"""

file_lock = threading.Lock()

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

MAX_RETRIES = 3
RETRY_DELAY = 2
CONNECTION_TIMEOUT = 10

def download_piece_from_peer(peer_host, peer_port, piece_hash, output_path, retry_peers=[], peer_id=None, file_name=None, chunk_index=None):
    retry_count = 0
    errors = []

    while retry_count < MAX_RETRIES:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(CONNECTION_TIMEOUT)
                logger = logging.getLogger(f'peer{peer_id}')
                s.connect((peer_host, int(peer_port)))
                
                request_message = f"REQUEST_PIECE|{piece_hash}"
                s.sendall(request_message.encode('utf-8'))

                with file_lock:
                    with open(output_path, 'wb') as output_file:
                        while chunk := s.recv(1024):
                            output_file.write(chunk)

                # Validate the downloaded chunk
                with file_lock:
                    with open(output_path, 'rb') as output_file:
                        downloaded_data = output_file.read()
                        downloaded_hash = compute_chunk_hash_3(downloaded_data, chunk_index, file_name)
                        if downloaded_hash != piece_hash:
                            raise ValueError("Downloaded chunk hash mismatch")
                
                logger.info(f"Successfully downloaded piece {piece_hash} from {peer_host}:{peer_port}")
                if peer_id is not None and file_name is not None:
                    update_torrent_with_chunks(peer_id, file_name)
                return True

        except (socket.timeout, ConnectionRefusedError) as e:
            retry_count += 1
            errors.append(f"Attempt {retry_count} failed: {str(e)}")
            logger.warning(f"Connection failed to {peer_host}:{peer_port}, retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
            
            # Try alternative peers if available
            if retry_peers and retry_count == MAX_RETRIES:
                logger.info("Trying alternative peers...")
                for alt_peer in retry_peers:
                    try:
                        alt_host = alt_peer["ip"]
                        alt_port = int(alt_peer["port"])
                        if download_piece_from_peer(alt_host, alt_port, piece_hash, output_path, [], peer_id, file_name, chunk_index):
                            return True
                    except Exception as alt_e:
                        errors.append(f"Alternative peer {alt_host}:{alt_port} failed: {str(alt_e)}")
                        continue

        except Exception as e:
            retry_count += 1
            errors.append(f"Attempt {retry_count} failed: {str(e)}")
            logger.error(f"Error downloading piece: {e}")
            time.sleep(RETRY_DELAY)

    logger.error(f"Failed to download piece {piece_hash} after {MAX_RETRIES} attempts. Errors: {errors}")
    return False

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
        logger = logging.getLogger(f'peer{peer_id}')
        torrent_path = f"peer{peer_id}/torrent.json"
        if not os.path.exists(torrent_path):
            logger.error(f"Torrent file not found: {torrent_path}")
            return

        chunks_path = f"peer{peer_id}/chunks"
        received_files_path = f"peer{peer_id}/received_files"

        if not os.path.exists(chunks_path):
            logger.error(f"Error: {chunks_path} not found.")
            return

        # Safely load and update the torrent.json file
        with file_lock:
            with open(torrent_path, 'r') as torrent_file:
                torrent_data = json.load(torrent_file)

            # Ensure pieces structure exists
            if "info" not in torrent_data or "pieces" not in torrent_data["info"]:
                logger.error(f"Error: Invalid torrent.json structure in {torrent_path}.")
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
                logger.info(f"Torrent.json updated successfully for peer {peer_id}")


            # print(f"Torrent.json updated successfully for peer {peer_id}.")
    except Exception as e:
        logger.error(f"Error updating torrent.json: {e}")

def download_file_concurrently(peer_id, file_name, pieces_to_peers, chunk_size):
    """
    Download multiple file pieces from peers concurrently, incorporating round-robin scheduling and retry handling.

    Args:
        peer_id (str): ID of the current peer.
        file_name (str): Name of the file to download.
        pieces_to_peers (dict): Mapping of piece hashes to lists of peers.
        chunk_size (int): Size of each chunk in bytes.
    """
    chunk_folder = f"peer{peer_id}/chunks"
    os.makedirs(chunk_folder, exist_ok=True)

    # Shared resources for thread safety
    download_tracker = set()  # Track completed downloads to avoid duplicates
    piece_status = {}  # Track download status of each piece
    failed_pieces = {}  # Track pieces that failed after all retries
    piece_status_lock = threading.Lock()  # Lock for thread-safe updates

    def is_piece_downloaded(piece_hash):
        piece_path = os.path.join(chunk_folder, f"{piece_hash}.chunk")
        return os.path.exists(piece_path)

    def download_piece(piece_hash, peer_list, piece_index):
        """
        Attempt to download a specific piece from multiple peers.
        """
        nonlocal download_tracker, failed_pieces
        random.shuffle(peer_list)  # Randomize peer order to ensure fairness

        output_path = os.path.join(chunk_folder, f"{piece_hash}.chunk")

        for peer_info in peer_list:
            peer_host = peer_info["ip"]
            peer_port = int(peer_info["port"])

            # Skip if the piece is already downloaded
            if piece_hash in download_tracker:
                return

            try:
                download_piece_from_peer(
                    peer_host=peer_host,
                    peer_port=peer_port,
                    piece_hash=piece_hash,
                    output_path=output_path,
                    peer_id=peer_id,
                    file_name=file_name,
                    chunk_index=piece_index
                )
                with piece_status_lock:
                    download_tracker.add(piece_hash)
                    piece_status[piece_hash] = True
                return
            except Exception as e:
                logger.error(f"Failed to download piece {piece_hash} from {peer_host}:{peer_port} - {e}")

        with piece_status_lock:
            piece_status[piece_hash] = False  # Mark as failed
            failed_pieces[piece_hash] = peer_list

    def round_robin_download():
        """
        Perform round-robin scheduling for downloading pieces from peers.
        """
        piece_queue = [
            (piece_hash, peer_list)
            for piece_hash, peer_list in pieces_to_peers.items()
            if not is_piece_downloaded(piece_hash)
        ]

        threads = []
        while piece_queue:
            piece_hash, peer_list = piece_queue.pop(0)
            piece_index = peer_list[0]["index"]  # Assume the index is consistent across peers
            thread = threading.Thread(target=download_piece, args=(piece_hash, peer_list, piece_index), daemon=True)
            threads.append(thread)
            thread.start()

            # Reinsert the piece to the end of the queue if not downloaded
            with piece_status_lock:
                if piece_hash not in download_tracker:
                    piece_queue.append((piece_hash, peer_list))

        for thread in threads:
            thread.join()

    # Perform initial round-robin download
    round_robin_download()

    # Retry failed pieces
    retry_count = 0
    while failed_pieces and retry_count < MAX_RETRIES:
        retry_count += 1
        logger.info(f"Retrying failed pieces (attempt {retry_count})")
        current_failed = failed_pieces.copy()
        failed_pieces.clear()

        threads = []
        for piece_hash, peer_list in current_failed.items():
            piece_index = peer_list[0]["index"]
            thread = threading.Thread(target=download_piece, args=(piece_hash, peer_list, piece_index), daemon=True)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        time.sleep(RETRY_DELAY)

    # Combine successfully downloaded pieces
    logger.info("Combining downloaded pieces...")
    piece_order = sorted(
        [p for p in pieces_to_peers.keys() if piece_status.get(p, False)],
        key=lambda piece_hash: pieces_to_peers[piece_hash][0]["index"]
    )
    combine_and_validate_pieces(
        received_folder=chunk_folder,
        output_file=f"peer{peer_id}/received_files/{file_name}",
        piece_order=piece_order
    )

    if failed_pieces:
        logger.error(f"Failed to download {len(failed_pieces)} pieces after all retries.")
        for piece_hash in failed_pieces:
            logger.error(f"Failed piece: {piece_hash}")

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
    try:
        # First check if we're the original uploader
        if check_file_exists(peer_id, file_name):
            logger.info("We are the original uploader of this file. No need to download.")
            return {}
            
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((tracker_host, tracker_port))
            request_message = f"PIECE_INFO_REQUEST|{file_name}"
            s.sendall(request_message.encode('utf-8'))

            # Read the data length header
            header = s.recv(1024).decode('utf-8')
            if not header.startswith("DATA_LENGTH|"):
                logger.error("Invalid response header from tracker")
                return {}
            data_length = int(header.split('|')[1])
            logger.info(f"Expecting {data_length} bytes of piece info data")

            # Receive the full JSON data in chunks
            received_data = b""
            while len(received_data) < data_length:
                chunk = s.recv(4096)
                if not chunk:
                    logger.error("Connection closed before receiving all data")
                    break
                received_data += chunk

            # Parse the JSON response
            if len(received_data) == data_length:
                pieces_to_peers = json.loads(received_data.decode('utf-8'))
                logger.info(f"Received pieces-to-peers mapping: {pieces_to_peers}")
                return pieces_to_peers
            else:
                logger.error("Received data size mismatch")
                return {}
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error requesting piece info: {e}")
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
        logger = logging.getLogger(f'peer{peer_id}')
        torrent_path = f"peer{peer_id}/torrent.json"
        chunks_folder = f"peer{peer_id}/chunks"

        if not os.path.exists(torrent_path):
            logger.error(f"{torrent_path} not found.")
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
            logger.info(f"Updated torrent.json successfully for peer {peer_id}")

        # Compute new info_hash
        new_info_hash = compute_info_hash(torrent_data["info"])
        logger.info(f"Computed new info_hash: {new_info_hash}")

        return torrent_data["info"]
    except Exception as e:
        logger.error(f"Error updating torrent.json: {e}")
        return None

def update_torrent_transfer_pieces(peer_id, file_name, file_size, chunk_path, chunk_size):
    """
    Update the torrent.json file after receiving file pieces.

    Args:
        peer_id (str): The ID of the peer receiving the pieces.
        file_name (str): The name of the file being reconstructed.
        file_size (int): The total size of the file in bytes.
        chunk_path (str): The directory path where the received chunks are stored.
        chunk_size (int): The size of each chunk in bytes.

    Returns:
        dict: The updated "info" section of the torrent.json file.
    """
    try:
        torrent_path = f"peer{peer_id}/torrent.json"
        if not os.path.exists(torrent_path):
            logger.error(f"{torrent_path} not found.")
            return None
        if not os.path.isdir(chunk_path):
            logger.error(f"Chunk path {chunk_path} is not a directory.")
            return None

        with file_lock:
            # Load the existing torrent.json content
            with open(torrent_path, 'r') as torrent_file:
                torrent_data = json.load(torrent_file)

            # Ensure the required structure exists in torrent.json
            if "info" not in torrent_data or "pieces" not in torrent_data["info"]:
                logger.error(f"Invalid torrent.json structure in {torrent_path}.")
                return None

            # Track existing pieces and files to prevent duplication
            existing_pieces = {piece["piece"]: piece for piece in torrent_data["info"]["pieces"]}
            existing_files = {tuple(file["path"]) for file in torrent_data["info"]["files"]}

            # Add metadata for the received file if not already present
            file_key = (f"peer{peer_id}", file_name)
            if file_key not in existing_files:
                file_metadata = {
                    "path": [f"peer{peer_id}", file_name],
                    "length": file_size
                }
                torrent_data["info"]["files"].append(file_metadata)
                logger.info(f"Added file metadata: {file_metadata}")

            # Process received chunks and update pieces
            for chunk_file in sorted(os.listdir(chunk_path)):  # Sort to ensure order
                chunk_file_path = os.path.join(chunk_path, chunk_file)
                if os.path.isfile(chunk_file_path):
                    with open(chunk_file_path, 'rb') as chunk:
                        chunk_data = chunk.read()
                        piece_hash = compute_chunk_hash_3(chunk_data, len(existing_pieces), file_name)
                        if piece_hash not in existing_pieces:
                            torrent_data["info"]["pieces"].append({
                                "piece": piece_hash,
                                "file_name": file_name,
                                "file_path": f"peer{peer_id}",
                                "index": len(existing_pieces)
                            })
                            logger.info(f"Added piece hash: {piece_hash}")

            # Save the updated torrent.json
            with open(torrent_path, 'w') as torrent_file:
                json.dump(torrent_data, torrent_file, indent=4)

            logger.info(f"Updated torrent.json successfully for peer {peer_id}.")
            return torrent_data["info"]

    except Exception as e:
        logger.error(f"Error updating torrent.json from pieces: {e}")
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
                logger.info(f"Created: {part_file_name}")
                part_num += 1
    except FileNotFoundError:
        logger.error("File not found. Please provide a valid file path.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

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
                logger.info(f"Added: {part_file}")
        logger.info(f"File combined into: {output_file}")
    except FileNotFoundError:
        logger.error("One or more part files not found. Please provide valid file paths.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

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
        logger.error(f"Error uploading file: {e}")
        
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
    # print(f"DEBUG: {chunk_data}, {chunk_index}, {file_name}, {expected_hash} \n {actual_hash}")
    logger.info(f"Validating chunk {chunk_index} in {file_name} and get {actual_hash == expected_hash}")
    
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
                                # print(f"Error: Piece {piece_hash} did not pass validation!")
                                continue
                            output.write(content)
                    else:
                        logger.info(f"Missing piece: {piece_hash}. File may be incomplete.")

        logger.info(f"File combined into {output_file} successfully.")
        
        # Update the torrent.json with the new file metadata
        peer_id = output_file.split('/')[0].replace("peer", "")  # Extract peer ID
        file_name = os.path.basename(output_file)
        file_size = os.path.getsize(output_file)

        torrent_path = f"peer{peer_id}/torrent.json"
        if not os.path.exists(torrent_path):
            logger.error(f"Error: {torrent_path} not found.")
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
            logger.info(f"Added file metadata to torrent.json: {file_metadata}")

        # Save updated torrent.json
        with open(torrent_path, 'w') as torrent_file:
            json.dump(torrent_data, torrent_file, indent=4)
            logger.info(f"Updated torrent.json successfully for peer {peer_id}.")
    except Exception as e:
        logger.error(f"Error combining pieces: {e}")

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
            logger.error(f"Torrent file {torrent_path} not found.")
            return
        if not os.path.exists(chunks_path):
            logger.error(f"Chunk path {chunks_path} not found.")
            return
        # Load the current torrent.json content
        with open(torrent_path, 'r') as torrent_file:
            torrent_data = json.load(torrent_file)
        # Ensure 'pieces' exists in the JSON structure
        if "info" not in torrent_data or "pieces" not in torrent_data["info"]:
            logger.error(f"Invalid torrent.json structure in {torrent_path}.")
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
                logger.info(f"Skipping non-file entry in chunks: {chunk_file}")

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
            logger.info(f"Tracker response: {response}")
    except Exception as e:
        logger.error(f"Error notifying tracker: {e}")

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
            
            logger.info(f"Uploading file: {file_name} with chunk size {chunk_size}")
            with open(file_path, 'wb') as f:
                while True:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    f.write(chunk)
            logger.info(f"File {file_name} was uploaded at {file_path}")
            
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
            logger.info(f"All pieces of {file_name} received successfully. Validating...")
            combine_and_validate_pieces(received_folder, f"peer{peer_id}/received_files/{file_name}")
            conn.sendall("TRANSFER_COMPLETE".encode('utf-8'))
        
        if data.startswith("REQUEST_PIECE"):
            _, piece_hash = data.split('|')
            piece_path = os.path.join(f"peer{peer_id}/chunks", f"{piece_hash}.chunk")
            if os.path.exists(piece_path):
                with open(piece_path, 'rb') as piece_file:
                    piece_data = piece_file.read()
                    conn.sendall(piece_data)
                logger.info(f"Sent piece {piece_hash} to peer.")
            else:
                conn.sendall("PIECE_NOT_FOUND".encode('utf-8'))
        else:
            logger.error(f"Unknown message received: {data}")
            conn.sendall("Invalid request".encode('utf-8'))
    except Exception as e:
        logger.error(f"Error handling peer connection: {e}")
    finally:
        conn.close()

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
            logger.info(f"Upload server running for peer {peer_id} on port {upload_port}")

            while True:
                conn, addr = upload_socket.accept()
                thread = threading.Thread(target=handle_peer_connection, args=(conn, peer_id), daemon=True)
                thread.start()
    except Exception as e:
        logger.error(f"Upload server error for peer {peer_id}: {e}")

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
            logger.info(f"Peer server listening on port {port}")
            while True:
                conn, addr = server_socket.accept()
                print(f"Connection received from {addr}")
                logger.info(f"Connection received from {addr}")
                threading.Thread(target=handle_peer_connection, args=(conn,peer_id)).start()
    except Exception as e:
        logger.error(f"Error in peer server: {e}")

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
                    logger.info(f"File {filename} sent successfully.")
                else:
                    logger.info(f"File {filename} does not exist.")
                    return
                s.shutdown(socket.SHUT_WR)  # Indicate file transfer is done

            response = s.recv(1024)
            logger.info(f"Response from peer: {response.decode('utf-8')}")
    except Exception as e:
        logger.error(f"Error connecting to peer: {e}")

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
            logger.info(response)
            _, peer_host = response.split('|')
            return peer_host
    except Exception as e:
        logger.error(f"Error registering with tracker: {e}")
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
            logger.info(response.decode('utf-8'))
        remove_peer_list_file(peer_id)
    except Exception as e:
        logger.error(f"Error while deregistering: {e}")

def remove_peer_list_file(peer_id):
    """
    Remove the peer_list.json file when the program exits.
    
    Args:
        peer_id (str): The peer ID to identify the folder.
    """
    folder_path = f"peer{peer_id}"
    file_path = os.path.join(folder_path, "peer_list.json")
    if (os.path.exists(file_path)):
        try:
            os.remove(file_path)
            logger.info(f"Successfully removed {file_path}")
        except Exception as e:
            logger.error(f"Failed to remove {file_path}: {e}")
    else:
        logger.warning(f"{file_path} does not exist.")

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
                logger.error("Invalid response header from tracker")
                return []
            data_length = int(header.split('|')[1])
            logger.info(f"Expecting {data_length} bytes of peer list data")

            # Receive the full data in chunks
            received_data = b""
            while len(received_data) < data_length:
                chunk = s.recv(4096)
                if not chunk:  # Connection closed prematurely
                    logger.error("Connection closed before receiving all data")
                    break
                received_data += chunk

            if len(received_data) != data_length:
                logger.error("Received data size mismatch")
                return []

            # Parse the JSON response
            peers = json.loads(received_data.decode('utf-8'))
            # Prepare a simplified list with peer ID and file names
            simplified_peer_list = []
            for peer in peers:
                peer_info = {
                    "peer_id": peer["peer_id"],
                    "files": [file_info["path"][-1] for file_info in peer["info_hash"]["files"]]  # Extract only the file names
                }
                simplified_peer_list.append(peer_info)

            # Ensure the directory for the peer exists
            folder_path = f"peer{peer_id}"
            os.makedirs(folder_path, exist_ok=True)

            # Write the simplified peer list to a JSON file in the folder
            file_path = os.path.join(folder_path, "peer_list.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(simplified_peer_list, f, ensure_ascii=False, indent=4)
            
            logger.info(f"Peer list saved to {file_path}")
            # Old
            # print(f"Received peer list: {peers}")
            # return peers
            # New
            return "Receiving peer list here"
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {e}")
        logger.error(f"Partial data received: {received_data.decode('utf-8')}")
    except Exception as e:
        logger.error(f"Error while requesting peer list: {e}")
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
            logger.error(f"{file_info} not found.")
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
                logger.error(f"Peer not ready for piece transfer: {response}")
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
                        logger.error(f"Error transferring piece {piece_name}: {response}")
                        return
            logger.info("All pieces sent successfully.")
    except Exception as e:
        logger.error(f"Error sending file pieces: {e}")

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
    logger.info("Shutting down the peer server...")
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
            logger.info(f"Initialized {torrent_file_path} for peer {peer_id}")
        else:
            print(f"{torrent_file_path} already exists for peer {peer_id}")
            logger.info(f"{torrent_file_path} already exists for peer {peer_id}")
    except Exception as e:
        print(f"Error initializing peer directory: {e}")
        logger.error(f"Error initializing peer directory: {e}")

# Add this new function after the existing helper functions
def check_file_exists(peer_id, file_name):
    """
    Check if the peer already has the complete and valid file.
    
    Args:
        peer_id (str): ID of the peer
        file_name (str): Name of the file to check
        
    Returns:
        bool: True if file exists and is valid, False otherwise
    """
    try:
        logger = logging.getLogger(f'peer{peer_id}')
        torrent_path = f"peer{peer_id}/torrent.json"
        
        if not os.path.exists(torrent_path):
            return False
            
        with open(torrent_path, 'r') as f:
            torrent_data = json.load(f)
            
        # Check if the file exists in the files list
        for file_info in torrent_data["info"]["files"]:
            if file_name == file_info["path"][-1]:
                logger.info(f"File {file_name} already exists in peer {peer_id}'s records")
                print(f"File {file_name} already exists in peer {peer_id}'s records")
                return True
                
        return False
    except Exception as e:
        logger.error(f"Error checking file existence: {e}")
        return False

# NEW 1
# Main script logic
if __name__ == "__main__":
    # Fetch the peer ID and port from command-line arguments
    peer_id = sys.argv[1]
    peer_port = int(sys.argv[2])
    piece_length = 8192  # Define the piece length (e.g., 5 bytes)

    # Initialize logger
    logger = setup_logger(peer_id)
    
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
            print(INSTRUCTION)
            command = input().strip()
            
            if command.startswith("UPLOAD"):
                _, file_path = command.split()
                if os.path.exists(file_path):
                    logger.info(f"Uploading file: {file_path}...")
                    print(f"Uploading file: {file_path}...")

                    # Use the upload_file function to split and store locally
                    upload_file(peer_id, file_path, chunk_size)
                    
                    # Update the torrent.json and compute the new info_hash
                    new_info_hash = update_torrent_json(peer_id, file_path, chunk_size)
                    if new_info_hash:
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.connect((tracker_host, tracker_port))
                                logger.info(f"Notifying tracker about upload for peer {peer_id}...")
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
                                logger.info(f"Tracker response: {response}")
                                print(f"Tracker response: {response}")
                        except Exception as e:
                            logger.error(f"Error notifying tracker: {e}")
                            print(f"Error notifying tracker: {e}")
                    else:
                        logger.error(f"Error: File {file_path} does not exist.")
                        print(f"Error: File {file_path} does not exist.")

            if command.startswith("DOWNLOAD"):
                _, file_name = command.split()
                
                # First check if we already have the file
                if check_file_exists(peer_id, file_name):
                    logger.info(f"Already have file {file_name} locally. Skipping download.")
                    print(f"Already have file {file_name} locally. Skipping download.")
                    continue
                
                pieces_to_peers = request_pieces_info(tracker_host, tracker_port, file_name)
                
                # Export the pieces_to_peers mapping to a text file
                export_file_path = f"peer{peer_id}/pieces_to_peers_{file_name}.txt"
                os.makedirs(os.path.dirname(export_file_path), exist_ok=True)
                
                try:
                    with open(export_file_path, 'w') as export_file:
                        json.dump(pieces_to_peers, export_file, indent=4)
                    logger.info(f"Exported pieces_to_peers mapping to {export_file_path}")
                    print(f"Exported pieces_to_peers mapping to {export_file_path}")
                except Exception as e:
                    logger.error(f"Error exporting pieces_to_peers mapping: {e}")
                    print(f"Error exporting pieces_to_peers mapping: {e}")
                
                if pieces_to_peers:
                    download_file_concurrently(peer_id, file_name, pieces_to_peers, chunk_size)
                    
                    # Prepare updated `info_hash`
                    torrent_path = f'peer{peer_id}/torrent.json'
                    with open(torrent_path, 'r') as torrent_file:
                        torrent_data = json.load(torrent_file)

                    # Track existing pieces
                    existing_pieces = {piece["piece"]: piece for piece in torrent_data["info"]["pieces"]}

                    # Add or update only new pieces
                    for piece_hash, peer_list in pieces_to_peers.items():
                        piece_index = peer_list[0]["index"]  # Get the correct index from the mapping
                        if piece_hash not in existing_pieces:
                            # Add new piece
                            torrent_data["info"]["pieces"].append({
                                "piece": piece_hash,
                                "file_name": file_name,
                                "file_path": f"peer{peer_id}",
                                "index": piece_index
                            })
                        else:
                            # Update existing piece metadata if necessary
                            piece = existing_pieces[piece_hash]
                            if "file_name" not in piece or piece["file_name"] != file_name:
                                piece["file_name"] = file_name
                            if "file_path" not in piece or piece["file_path"] != f"peer{peer_id}":
                                piece["file_path"] = f"peer{peer_id}"
                            if "index" not in piece or piece["index"] != piece_index:
                                piece["index"] = piece_index

                    # Save the updated torrent.json
                    with open(torrent_path, 'w') as torrent_file:
                        json.dump(torrent_data, torrent_file, indent=4)

                    logger.info(f"Updated torrent.json successfully for peer {peer_id}.")

                    # Notify the tracker with the updated `info_hash`
                    new_info_hash = torrent_data["info"]
                    
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect((tracker_host, tracker_port))
                            logger.info(f"Notifying tracker about updated peer info for peer {peer_id}...")
                            
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
                            logger.info(f"Tracker response: {response}")
                    except Exception as e:
                        logger.error(f"Error notifying tracker: {e}")
                else:
                    logger.error("No piece info available for download.")
            elif command == "EXIT":
                logger.info("Exiting...")
                deregister_from_tracker(tracker_host, tracker_port, peer_id)
                break
            request_peers_list(tracker_host, tracker_port, peer_id)  
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        deregister_from_tracker(tracker_host, tracker_port, peer_id)


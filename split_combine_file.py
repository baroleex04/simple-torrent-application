import os

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


# Example usage:
if __name__ == "__main__":
    choice = input("Enter 's' to split a file or 'c' to combine files: ").strip().lower()

    if choice == 's':
        file_to_split = input("Enter the file path to split: ").strip()
        size = int(input("Enter the chunk size in bytes (e.g., 1024 for 1KB): ").strip())
        split_file(file_to_split, size)
    elif choice == 'c':
        num_parts = int(input("Enter the number of parts to combine: ").strip())
        part_files = [input(f"Enter path for part {i+1}: ").strip() for i in range(num_parts)]
        output_path = input("Enter the output file path: ").strip()
        combine_files(part_files, output_path)
    else:
        print("Invalid choice. Please enter 's' to split or 'c' to combine.")

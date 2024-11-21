from datetime import datetime

# Get the current second with the decimal part
current_second_with_fraction = datetime.now().strftime("%S.%f")
print("Second with decimal:", current_second_with_fraction)
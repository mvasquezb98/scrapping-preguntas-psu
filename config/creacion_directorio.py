import os

def create_output_folder(folder):
  os.makedirs(folder, exist_ok=True)
  return folder

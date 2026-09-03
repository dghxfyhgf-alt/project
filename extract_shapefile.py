import zipfile
import os

zip_path = r"C:\Users\ASUS\Downloads\ExportShapeFile.zip"
extract_dir = r"C:\Users\ASUS\Downloads\ExportShapeFile_Extracted"

os.makedirs(extract_dir, exist_ok=True)

with zipfile.ZipFile(zip_path, 'r') as z:
    print('Files in zip:')
    for info in z.infolist():
        print(f'  {info.filename} ({info.file_size} bytes)')
    z.extractall(extract_dir)

print('Extracted successfully')
print('\nExtracted files:')
for root, dirs, files in os.walk(extract_dir):
    for f in files:
        full = os.path.join(root, f)
        size = os.path.getsize(full)
        print(f'  {full} ({size} bytes)')
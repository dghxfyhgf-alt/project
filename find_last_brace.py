with open(r'C:\Users\ASUS\Documents\Default Project\frontend\lib\map_page.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the last '}' in the file
last_brace_pos = content.rfind('\n}')
print('Last } at position: ' + str(last_brace_pos))
print('Last 200 chars: ' + repr(content[-200:]))
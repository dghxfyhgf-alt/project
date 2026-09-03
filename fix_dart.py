with open(r'C:\Users\ASUS\Documents\Default Project\frontend\lib\map_page.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the last occurrence of "      } else {" (the else block in _parseIntent)
else_idx = content.rfind('      } else {')
print(f'Else block at: {else_idx}')

if else_idx >= 0:
    # Keep everything before the else block
    content = content[:else_idx]
    
    with open(r'C:\Users\ASUS\Documents\Default Project\frontend\lib\map_page.dart', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('Truncated file successfully')
else:
    print('Could not find else block')
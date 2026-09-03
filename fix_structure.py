with open(r'C:\Users\ASUS\Documents\Default Project\frontend\lib\map_page.dart', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# The class ends at line 885 (index 884) with '  }'
# The helper methods were inserted AFTER the class (starting at line 886)
# We need to:
# 1. Keep lines 0-883 (up to the class closing brace)
# 2. Add all helper methods
# 3. Add the class closing brace
# 4. Keep the helper classes at the end

# Find the class closing brace (indent 2, '  }')
class_end_idx = -1
for i, line in enumerate(lines):
    if line.strip() == '}' and i > 800:
        indent = len(line) - len(line.lstrip())
        if indent == 2:  # Class level indent
            class_end_idx = i
            break

print(f'Class ends at line {class_end_idx + 1}')

# The duplicate helper methods start after the class
# Find where the duplicate methods start (after the class closing brace)
duplicate_start = -1
for i in range(len(lines)):
    if i > 885 and 'PolylineLayer _buildRouteLayer()' in lines[i]:
        print(f'Duplicate methods start at line {i+1}')
        break

# Keep lines 0 to class_end_idx (inclusive of class closing brace)
# But we need to insert helper methods BEFORE the closing brace
# So: lines[0:class_end_idx] + helper_methods + ['  }\n'] + lines[class_end_idx+1:]

# Find where the duplicate methods start (after the class)
# The class ends at index where '  }' at indent 2
class_end_idx = -1
brace_count = 0
in_class = False
for i, line in enumerate(lines):
    if 'class _MapPageState' in line:
        in_class = True
    if in_class:
        for ch in line:
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    print(f'Class ends at line {i+1} (index {i})')
                    break

# Let's just find the last '  }' before the helper classes
for i in range(len(lines)-1, 800, -1):
    if lines[i].strip() == '}' and len(lines[i]) - len(lines[i].lstrip()) == 2:
        if i > 800:
            print(f'Class ends at line {i+1}')
            break

"
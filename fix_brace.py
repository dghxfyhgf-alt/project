with open(r'C:\Users\ASUS\Documents\Default Project\frontend\lib\map_page.dart', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Line 679 (index 678) is '    );' - end of Scaffold
# Line 680 (index 679) is empty
# Line 681 (index 680) is comment
# Line 685 (index 684) is '  PolylineLayer _buildRouteLayer() {' - first helper method
# Need to insert '  }\n' before line 681 (the comment section)

# Insert at index 680 (after line 679, before line 680)
lines.insert(680, '  }\n')

with open(r'C:\Users\ASUS\Documents\Default Project\frontend\lib\map_page.dart', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Added missing closing brace for build method')
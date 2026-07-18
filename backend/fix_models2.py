import re

with open("models.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # 跳过已经有长度的String (String(xxx))
    if 'String(' in line and 'String,' not in line:
        new_lines.append(line)
        continue
    
    # 匹配 Column(String, 或 Column(String)
    # 替换为 Column(String(255),
    pattern1 = r'Column\(String([,\)])'
    if re.search(pattern1, line):
        line = re.sub(pattern1, r'Column(String(255)\1', line)
    
    # 匹配 Column("name", String, 或 Column("name", String)
    pattern2 = r'Column\((["\'][^"\']+["\']), String([,\)])'
    if re.search(pattern2, line):
        line = re.sub(pattern2, r'Column(\1, String(255)\2', line)
    
    # 匹配类似 machine_state = Column(String) 这种末尾的
    pattern3 = r'= Column\(String\)'
    if re.search(pattern3, line):
        line = re.sub(pattern3, r'= Column(String(255))', line)
    
    new_lines.append(line)

with open("models.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Done!")

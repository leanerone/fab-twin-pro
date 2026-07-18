import re

with open("models.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if '= PK_INT' in line:
        # 获取变量名
        match = re.match(r'\s*(\w+)\s*=\s*PK_INT', line)
        if match:
            var_name = match.group(1)
            indent = line[:len(line) - len(line.lstrip())]
            new_line = f'{indent}{var_name} = Column(Integer, Identity(start=1, increment=1), primary_key=True)\n'
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    else:
        new_lines.append(line)

# 移除PK_INT的定义
content = ''.join(new_lines)
content = content.replace('PK_INT = Column(Integer, Identity(start=1, increment=1), primary_key=True)\n', '')

with open("models.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done!")

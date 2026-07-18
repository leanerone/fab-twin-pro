import re

with open("models.py", "r", encoding="utf-8") as f:
    content = f.read()

# 替换所有的 Column(Integer, primary_key=True, autoincrement=True) 为 PK_INT
# 注意需要处理不同的格式，比如换行的情况

# 简单替换：一行内的
content = re.sub(
    r'Column\(Integer, primary_key=True, autoincrement=True\)',
    'PK_INT',
    content
)

# 也处理可能有空格变化的情况
content = re.sub(
    r'Column\(\s*Integer\s*,\s*primary_key\s*=\s*True\s*,\s*autoincrement\s*=\s*True\s*\)',
    'PK_INT',
    content
)

with open("models.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done! Replaced autoincrement columns with PK_INT")

# 验证一下
count = content.count('PK_INT')
print(f"Found {count} PK_INT usages")

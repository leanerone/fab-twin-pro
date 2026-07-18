import re

with open("models.py", "r", encoding="utf-8") as f:
    content = f.read()

# 替换 Column(String, 为 Column(String(255),
# 但要注意已经有长度的String和带列名的情况（如 Column("LEVEL", String, ...)

# 模式1: Column(String, ...) -> Column(String(255), ...)
content = re.sub(r'Column\(String,', 'Column(String(255),', content)

# 模式2: Column("name", String, ...) -> Column("name", String(255), ...)
content = re.sub(r'Column\((["\'][^"\']+["\']), String,', r'Column(\1, String(255),', content)

# 模式3: Column(String, ...) 中如果有 default= 的情况也需要处理 - 已被模式1覆盖

with open("models.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done! All String columns now have length 255.")

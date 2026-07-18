import docx

def read_docx(filepath):
    doc = docx.Document(filepath)
    full_text = []
    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text)
    return '\n'.join(full_text)

print("=== PODOPENER.docx ===")
print(read_docx("PODOPENER.docx"))
print("\n\n=== alarmnew.docx ===")
print(read_docx("alarmnew.docx"))

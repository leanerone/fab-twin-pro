import os
import sys
import oracledb

DB_USER = "fabtwin"
DB_PASSWORD = "fabtwin"
DB_HOST = "localhost"
DB_PORT = 1521
DB_SERVICE = "ORCLPDB"

SQL_FILE = os.path.join(os.path.dirname(__file__), "..", "sql", "init_oracle_db.sql")

def main():
    print(f"Connecting to Oracle: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_SERVICE}")
    
    dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE)
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
    cursor = conn.cursor()
    
    print("Connected! Reading SQL file...")
    
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    statements = []
    current_stmt = []
    
    for line in sql_content.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--") or stripped.startswith("/*") or stripped.startswith("SET "):
            continue
        if stripped.endswith(";"):
            current_stmt.append(stripped[:-1])
            stmt = "\n".join(current_stmt).strip()
            if stmt:
                statements.append(stmt)
            current_stmt = []
        else:
            current_stmt.append(line)
    
    if current_stmt:
        stmt = "\n".join(current_stmt).strip()
        if stmt and stmt != "/":
            statements.append(stmt)
    
    print(f"Found {len(statements)} SQL statements to execute")
    
    success = 0
    errors = 0
    
    for i, stmt in enumerate(statements):
        try:
            cursor.execute(stmt)
            success += 1
            if (i + 1) % 100 == 0:
                print(f"  Progress: {i+1}/{len(statements)} statements executed...")
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error at statement {i+1}: {e}")
                print(f"  SQL: {stmt[:200]}...")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"\nDone! Success: {success}, Errors: {errors}")

if __name__ == "__main__":
    main()

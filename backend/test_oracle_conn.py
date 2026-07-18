import oracledb

try:
    conn = oracledb.connect(mode=oracledb.SYSDBA)
    print('连接成功！')
    print('Oracle版本:', conn.version)
    
    cursor = conn.cursor()
    cursor.execute("SELECT name, open_mode FROM v$pdbs")
    print('PDB列表:')
    for row in cursor:
        print(f'  {row[0]} - {row[1]}')
    
    cursor.close()
    conn.close()
except Exception as e:
    print('连接失败:', e)
    import traceback
    traceback.print_exc()

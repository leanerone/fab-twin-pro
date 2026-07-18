import sys
sys.path.insert(0, ".")

from sqlalchemy.schema import CreateTable
from database import engine
from models import Base

for table in Base.metadata.sorted_tables:
    ddl = CreateTable(table).compile(dialect=engine.dialect)
    ddl_str = str(ddl)
    if 'VARCHAR2,' in ddl_str or 'VARCHAR2\n' in ddl_str:
        print(f"Problem table: {table.name}")
        print(ddl_str)
        print("---")

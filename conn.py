"""
Connects to a SQL database using pyodbc
"""
import pyodbc
SERVER = 'NG3523819W1'
DATABASE = 'eyregtech'
USERNAME = 'eyregtech'
PASSWORD = '@DigitalEng123'
connectionString = f'DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};TrustServerCertificate=yes'
conn = pyodbc.connect(connectionString)
SQL_QUERY = """
SELECT 
TOP 5 id, name, position from Employees;
"""
cursor = conn.cursor()
cursor.execute(SQL_QUERY)

records = cursor.fetchall()
for r in records:
    print(f"{r.id}\t{r.name}\t{r.position}")
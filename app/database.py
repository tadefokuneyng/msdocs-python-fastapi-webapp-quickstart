import os
from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv
load_dotenv()
# Define your SQL Server connection URL
# DATABASE_URL = "mssql+pyodbc://eyregtech:DigitalEng123@NG3523819W1/eyregtech?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
SERVER = os.getenv('DB_SERVER')
DATABASE = os.getenv('DB_NAME')
USERNAME = os.getenv('DB_USERNAME')
PASSWORD = os.getenv('DB_PASSWORD')
# connectionString = f'DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};TrustServerCertificate=yes'
DATABASE_URL = f"mssql+pyodbc://{USERNAME}:{PASSWORD}@{SERVER}/{DATABASE}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
print(DATABASE_URL)
# Create the SQLAlchemy engine
engine = create_engine(DATABASE_URL, echo=True)

# Dependency for database sessions
def get_db():
    with Session(engine) as session:
        yield session

# Function to create tables
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# Function to drop tables
def drop_db_and_tables():
    SQLModel.metadata.drop_all(engine)


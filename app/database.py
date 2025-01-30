from sqlmodel import SQLModel, create_engine, Session

# Define your SQL Server connection URL
DATABASE_URL = "mssql+pyodbc://eyregtech:DigitalEng123@NG3523819W1/eyregtech?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

# Create the SQLAlchemy engine
engine = create_engine(DATABASE_URL, echo=True)

# Dependency for database sessions
def get_db():
    with Session(engine) as session:
        yield session

# Function to create tables
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

from sqlmodel import SQLModel, create_engine, Session, select
from sqlmodel import Field
from typing import Optional

# Define your database connection string using ODBC
DATABASE_URL = "mssql+pyodbc://eyregtech:DigitalEng123@NG3523819W1/eyregtech?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

# Create the SQLAlchemy engine with SQLModel
engine = create_engine(DATABASE_URL, echo=True)

# Test model to check connection
class Employee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    position: str

# Create the session
def test_connection():
    try:
        # Create the test table if it doesn't exist
        SQLModel.metadata.create_all(engine)

        # Start a session
        with Session(engine) as session:
            # Add a test record
            new_record = Employee(name="Tomiwa", position="Manager" )
            session.add(new_record)
            session.commit()

            # Query to verify the data was inserted
            statement = select(Employee).where(Employee.name == "Tomiwa")
            result = session.exec(statement).first()
            
            if result:
                print(f"Connection Successful! Record found: {result}")
            else:
                print("No record found, connection might have an issue.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_connection()

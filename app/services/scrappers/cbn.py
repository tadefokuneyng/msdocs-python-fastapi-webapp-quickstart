from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Literal
import re
import requests
from google.cloud import storage
import os
from google.cloud import vision_v1
from google.cloud.vision_v1 import types
from openai import OpenAI
from dotenv import load_dotenv

from diskcache import Cache
from datetime import datetime

import pytesseract
from pdf2image import convert_from_path

from app.database import get_db
from app.models import AgentLog
import threading


load_dotenv()

llm = OpenAI(
    # api_key=os.getenv("OPENAI_API_KEY"),    
)
os.environ["GCLOUD_PROJECT"] = "eyailab"

RULEBOOK_API_AUTH_URL = os.getenv("RULEBOOK_API_AUTH_URL")
RULEBOOK_API_AUTH_USERNAME = os.getenv("RULEBOOK_API_AUTH_USERNAME")
RULEBOOK_API_AUTH_PASSWORD = os.getenv("RULEBOOK_API_AUTH_PASSWORD")
RULEBOOK_API_INVENTORY_URL = os.getenv("RULEBOOK_API_INVENTORY_URL")
RULEBOOK_API_AI_LOG_URL = os.getenv("RULEBOOK_API_AI_LOG_URL")
RULEBOOK_API_AUTH_OTP = os.getenv("RULEBOOK_API_AUTH_OTP")
RULEBOOK_API_KEY = os.getenv("RULEBOOK_API_KEY")

BASE_URL = os.getenv("BASE_URL")

# Create a TTL cache with a single item
token_cache = Cache("./.cache/auth")
circulars_run_cache = Cache("./.cache/run/circulars")

def set_auth(auth):
    expires_at = datetime.strptime(auth["expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    ttl = (expires_at - now).total_seconds()
    
    if ttl > 0:  # Ensure TTL is valid
        token_cache.set("token", auth["token"], expire=ttl)  # Set with expiration time

def get_token():
    return token_cache.get("token")  # Returns None if expired or not set

def set_run_status(type, id):
    if type == 'circulars':
        circulars_run_cache.set("id", id)  # Set with expiration time

def get_run_status(type):
    if type == 'circulars':
        return circulars_run_cache.get("id")  # Returns None if expired or not set

class Circular:
    reference:str
    link:str
    description:str
    date:str
    content:str

class Rule(BaseModel):
    id: str
    title: str
    description: str
    units: list[Literal['IT', 'RISK','COMPLIANCE']]
    type: Literal['CIRCULAR', 'GUIDELINE', 'UPDATED GUIDELINE']
    date: str

class Rules(BaseModel):
    rules: list[Rule]

class Section(BaseModel):
    title: str
    description: str
    action_plan: str
    sanctions: str
    requires_regulatory_returns: bool
    frequency_of_returns: str
    units: list[Literal['IT', 'RISK','COMPLIANCE']]
    timeline_date: str

class Regulation(BaseModel):
    title: str
    reference:str
    link:str
    type: Literal['ACT', 'GUIDELINES', 'CIRCULARS']
    description:str
    release_date:str
    effective_date:str
    last_ammend_date:str
    regulatory_status:Literal['ACTIVE', 'REPEALED', 'SUPERSEDED']
    sections: list[Section]
 
def upload_to_gcs(pdf_path, destination_blob_name):
    storage_client = storage.Client()
    bucket_name = 'eyailab-cbn'
    bucket = storage_client.bucket(bucket_name)
    """Uploads a file to Google Cloud Storage and returns the public URL."""
    blob = bucket.blob(destination_blob_name)
    #generation_match_precondition = 0
    #blob.upload_from_filename(pdf_path, if_generation_match=generation_match_precondition)
    blob.upload_from_filename(pdf_path)
    # Make the blob publicly accessible
    blob.make_public()
    print(
        f"File {pdf_path} uploaded to {destination_blob_name}."
    )
    # Get the GCS URI
    gcs_uri = f"gs://{bucket_name}/{destination_blob_name}"
    return gcs_uri

def upload_content_to_gcs(content, destination_blob_name):
    storage_client = storage.Client()
    bucket_name = 'eyailab-cbn'
    bucket = storage_client.bucket(bucket_name)
    """Uploads a file to Google Cloud Storage and returns the public URL."""
    blob = bucket.blob(destination_blob_name)
    #generation_match_precondition = 0
    #blob.upload_from_filename(pdf_path, if_generation_match=generation_match_precondition)
    blob.upload_from_string(content)
    # Make the blob publicly accessible
    blob.make_public()
    print(
        f"File uploaded to {destination_blob_name}."
    )
    # Get the GCS URI
    gcs_uri = f"gs://{bucket_name}/{destination_blob_name}"
    return gcs_uri

def extract_text_from_pdf(pdf_url):
    # Set up the Vision API client
    client = vision_v1.ImageAnnotatorClient()
    page_limit = 5

    # Construct the request
    input_config = types.InputConfig(
        gcs_source=types.GcsSource(uri=pdf_url),
        mime_type='application/pdf'
    )
    feature = types.Feature(type=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION)

    extracted_text = ""
    page = 1
    while True:
        # Create the file request
        file_request = vision_v1.types.AnnotateFileRequest(
            input_config=input_config,
            features=[feature],
            pages=list(range(page, page + page_limit))
        )
        # Batch the requests
        batch_request = vision_v1.types.BatchAnnotateFilesRequest(requests=[file_request])
        # Make the request to the Vision API
        response = client.batch_annotate_files(request=batch_request)
        # Extract the text from the response
        if not response.responses:
            break
        for file_response in response.responses:
            for page_response in file_response.responses:
                if page_response.full_text_annotation.text:
                    extracted_text += page_response.full_text_annotation.text
        if len(file_response.responses) < page_limit:
            break
        page += page_limit
    
    return extracted_text

def extract_rules(circular: Circular) -> Rules:
  prompt = """
  As a compliance officer or regulatory analyst within a financial institution, your objective is to break down regulatory communications issued by the Central Bank, that you received from the user into individual actionable compliance measures (rules). 
 
  title: Identify the document reference number.
  reference: Identify the document reference number.
  link: The URL of the document.
  type: One of ['ACT', 'GUIDELINES', 'CIRCULARS'] that describes the document type.
  description: A brief summary of the document.
  release_date: Identify the date of document.
  effective_date: Identify the effective date of the regulation.
  last_ammend_date: Identify the last amendment date of the regulation.
  regulatory_status: On of ['ACTIVE', 'REPEALED', 'SUPERSEDED'] that describes the status of the regulation.

  List out all phrases or statements that meet the following criteria as the communication action points:
  - Statements that prohibit explicitly defined actions or behaviors. 
  - Statements that outline specific requirements, obligations, or responsibilities.
  - Deadlines, timelines, or effective dates mentioned in the circular.
  - Implement regulatory changes or comply with new requirements.
  - Reporting to regulatory authorities or maintaining documentation.
  - References to training or awareness programs that may be required for compliance. 
  - Exceptions or exemptions mentioned in the circular. 
  - Guidance on risk management practices or control measures
  - Outline of the consequences of non-compliance. 

  Review the action points for actionability within FSI compliance context and match items with similarity rating of more than 50% and merge them into one statement. 
  List out the final list of action points. 
  For each of the final list of action points:
  - compose the full instructions relating to it as stated in the document as a rule:
  -- Identify id of the rule as [document reference number]-[rule number]
  -- Identify Title, detailed information including all instructions, references, action plan, sactions, if regulatory returns are required, frequency of returns, recommendations and dates as Rule Description, Date as [date of document], all applicable Unit(s) that needs the rule and the Type.
  title: str
    description: str
    action_plan: str
    sanctions: str
    requires_regulatory_returns: bool
    frequency_of_returns: str
    units: list[Literal['IT', 'RISK','COMPLIANCE']]
    type: Literal['CIRCULAR', 'GUIDELINE', 'UPDATED GUIDELINE']
    timeline_date: str

  Convert the final list of action points into the given structure.
  """
  content = f"""
  #Reference: {circular.reference}
  #Link: {circular.link}
  #Description: {circular.description}
  #Publish Date: {circular.date}
  **Circular Content:**
  {circular.content}
  """
  completion = llm.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[
      {"role": "system", "content": prompt},
      {"role": "user", "content": content}
    ],
    response_format=Regulation
  )

  return completion.choices[0].message.parsed

def do_main():
    #token = get_token()  # Should return "Thisistokenstr"
    #if token == None:
    #    request_auth()
    #    token = get_token()
    # URL of the page to scrape
    url = "https://www.cbn.gov.ng/api/GetAllCirculars?format=json"

    # Send a GET request to the page
    response = requests.get(url)
    response.raise_for_status()  # Check that the request was successful

    # Find all circular entries
    all_entries = response.json()
    if not all_entries:
        raise ValueError("No circulars found")
    
    last_run_id = get_run_status('circulars')
    if last_run_id == None:
        last_run_id = all_entries[0].get('id')
        set_run_status('circulars', last_run_id)
        raise ValueError("System is running for the first time, next available circular will be processed")

    new_entries = []
    for entry in all_entries:
        if entry.get('id') == last_run_id:
            break
        new_entries.append(entry)
    new_entries.reverse()

    circular_entries = new_entries[0:1] # Select the first 10 entries

    if not new_entries:
        raise ValueError("No new circulars found")

    
    circular = Circular
    for entry in circular_entries:
        ref = entry.get('refNo')
        linkHref = 'https://www.cbn.gov.ng' + entry.get('link')
        linkText = entry.get('title')
        date_str = entry.get('documentDate')

        file_name = linkHref.split('/')[-1]
        safe_file_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', file_name)

        response = requests.get(linkHref)
        response.raise_for_status()  # Ensure the request was successful

        # Save the PDF to a file
        pdf_path = 'app/static/cbn/' + safe_file_name
        with open(pdf_path, "wb") as file:
          content = response.content
          file.write(content)
        pdf_url = '/static/cbn/' + safe_file_name
        # pdf_url = upload_to_gcs(pdf_path, safe_file_name)

        #This is the one I am using
        # pdf_url = upload_content_to_gcs(response.content, safe_file_name)
        # text = extract_text_from_pdf(pdf_url)

        # Convert PDF pages to images
        images = convert_from_path(pdf_path)

        # Extract text from each image
        text = ""
        for i, image in enumerate(images):
            text += f"\n--- Page {i+1} ---\n"
            text += pytesseract.image_to_string(image)

        # Print or save extracted text

        #print(f"Title: {ref}")
        #print(f"Link: {linkHref}")
        #print(f"Description: {linkText}")
        #print(f"Published Date: {date_str}")
        #print(f"Content: {text}")
        #print("------")

        circular.reference = ref
        circular.link = pdf_url
        circular.description = linkText
        circular.date = date_str
        circular.content = text

        regulation: Circular = extract_rules(circular)
        #regulation_json = regulation.model_dump_json();
        date_format = "%d/%m/%Y"
        # Prepare the payload for the API request
        payload = {
            "title": regulation.title,
            "reference": regulation.reference,
            #"link": BASE_URL + regulation.link,
            "link": linkHref,
            "type": regulation.type,
            "description": regulation.description,
            "releaseDate": format_date_as_string(regulation.release_date),  # Format release_date as yyyy-mm-dd
            "effectiveDate": format_date_as_string(regulation.effective_date or regulation.release_date),
            "lastAmmendDate": format_date_as_string(regulation.last_ammend_date or regulation.release_date),
            "regulatoryStatus": regulation.regulatory_status,
            "aiRegulationSectionDtos": [
            {
            "aiRegulationDraftId": 0,
            "title": section.title,
            "description": section.description,
            "actionPlan": section.action_plan,
            "sanctions": section.sanctions,
            "requiresRegulatoryReturns": str(section.requires_regulatory_returns),
            "frequencyOfReturns": section.frequency_of_returns or "NA",
            "units": ','.join(section.units),
            "timelineDate": format_date_as_string(section.timeline_date or regulation.release_date)
            } for section in regulation.sections
            ]
        }

        print(payload)

        # Send the API request
        response = requests.post(
            RULEBOOK_API_INVENTORY_URL,
            headers={
            'accept': 'text/plain',
            #'Authorization': f'Bearer {token}',
            'x-api-key': RULEBOOK_API_KEY,
            'Content-Type': 'application/json'
            },
            json=payload
        )

        response.raise_for_status()  # Ensure the request was successful
        result = response.json()
        if result.get("isSuccess") == True:
            set_run_status('circulars', entry.get('id'))
            print("Regulation successfully uploaded.")
        print(result)
        """print("Regulation successfully uploaded.")

        print(f"Title: {regulation.title}")
        print(f"Reference: {regulation.reference}")
        print(f"Link: {regulation.link}")
        print(f"Type: {regulation.type}")
        print(f"Description: {regulation.description}")
        print(f"Release Date: {regulation.release_date}")
        print(f"Effective Date: {regulation.effective_date}")
        print(f"Last Amendment Date: {regulation.last_ammend_date}")
        print(f"Regulatory Status: {regulation.regulatory_status}")
        print("------SECTIONS------")
        for section in regulation.sections:
            print(f"Title: {section.title}")
            print(f"Description: {section.description}")
            print(f"Action Plan: {section.action_plan}")
            print(f"Sanctions: {section.sanctions}")
            print(f"Requires Regulatory Returns: {section.requires_regulatory_returns}")
            print(f"Frequency of Returns: {section.frequency_of_returns}")
            print(f"Units: {section.units}")
            print(f"Timeline Date: {section.timeline_date}")
            print("------")
        print("------")"""

def format_date_as_string(date):
    if isinstance(date, datetime):
        return date.strftime("%Y-%m-%d")
    elif isinstance(date, str):
        try:
            # Try parsing as yyyy-mm-dd
            parsed_date = datetime.strptime(date, "%Y-%m-%d")
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            try:
                # Try parsing as dd/mm/yyyy
                parsed_date = datetime.strptime(date, "%d/%m/%Y")
                return parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                return date  # Return the original string if parsing fails
    else:
        return date  # Return the original value if it's neither a string nor a datetime
def log_agent_request(status=None, error=None):
    try:
        #token = get_token()  # Should return "Thisistokenstr"
        #if token == None:
        #    request_auth()
        #    token = get_token()

        # Send the API request
        response = requests.post(
            RULEBOOK_API_AI_LOG_URL,
            headers={
            'accept': 'text/plain',
            #'Authorization': f'Bearer {token}',
            'x-api-key': RULEBOOK_API_KEY,
            'Content-Type': 'application/json'
            },
            json={
            "lastRunTime": datetime.now(timezone.utc).isoformat(sep='T', timespec='seconds'),
            "runStatus": status,
            "regulationSite": "Central Bank of Nigeria",
            "errorMessage": (error if error else ""),
            }
        )

        response.raise_for_status()  # Ensure the request was successful
        result = response.json()
        print(result)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while logging the agent request: {e}")
        if error:
            print(f"Additional error information: {error}")
def request_auth():
    response = requests.post(
        RULEBOOK_API_AUTH_URL,
        headers={
            'accept': '*/*',
            'Content-Type': 'application/json'
        },
        json={
            "username": RULEBOOK_API_AUTH_USERNAME,
            "password": RULEBOOK_API_AUTH_PASSWORD,
            "otp": RULEBOOK_API_AUTH_OTP
        }
    )

    response.raise_for_status()  # Ensure the request was successful
    result = response.json()["result"]
    set_auth({"expires": result["expiration"], "token": result["token"]})

def run_task():
    time = 300 # Every 5 minutes
    log_agent_request(0)
    try:
        do_main()
        log_agent_request(1)
    except Exception as e:  
        log_agent_request(2, str(e))
        print(e)
        if isinstance(e, requests.exceptions.HTTPError) and 400 <= e.response.status_code < 500:
            print("Client Error:", e.response.status_code, e.response.text)
            time = 60 # Every 1 minutes
    print(get_run_status('circulars'))
    threading.Timer(time, run_task).start()  # Every 5 minutes

if __name__ == '__main__':
    run_task()
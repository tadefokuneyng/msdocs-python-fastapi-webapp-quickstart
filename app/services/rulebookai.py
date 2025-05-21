from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Literal
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv

from diskcache import Cache
from datetime import datetime

import pytesseract
from pdf2image import convert_from_path

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

BASE_URL = os.getenv("BASE_URL")

# Create a TTL cache with a single item
token_cache = Cache("./.cache/auth")

def set_auth(auth):
    expires_at = datetime.strptime(auth["expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    ttl = (expires_at - now).total_seconds()
    
    if ttl > 0:  # Ensure TTL is valid
        token_cache.set("token", auth["token"], expire=ttl)  # Set with expiration time

def get_token():
    return token_cache.get("token")  # Returns None if expired or not set

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
    token = get_token()  # Should return "Thisistokenstr"
    if token == None:
        request_auth()
        token = get_token()
    # URL of the page to scrape
    url = "https://www.cbn.gov.ng/api/GetAllCirculars?format=json"

    # Send a GET request to the page
    response = requests.get(url)
    response.raise_for_status()  # Check that the request was successful

    # Find all circular entries
    circular_entries = response.json()[0:1] # Select the first 10 entries
    # print(circular_entries)

    # Extract and print the details of the last 10 circulars
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
            "link": BASE_URL + regulation.link,
            "type": regulation.type,
            "description": regulation.description,
            "releaseDate": datetime.strptime(regulation.release_date, date_format).strftime("%Y-%m-%d"),
            "effectiveDate": datetime.strptime(regulation.effective_date or regulation.release_date, date_format).strftime("%Y-%m-%d"),
            "lastAmmendDate": datetime.strptime(regulation.last_ammend_date or regulation.release_date, date_format).strftime("%Y-%m-%d"),
            "regulatoryStatus": regulation.regulatory_status,
            "aiRegulationSectionDtos": [
            {
                "aiRegulationDraftId": 0,
                "title": section.title,
                "description": section.description,
                "actionPlan": section.action_plan,
                "sanctions": section.sanctions,
                "requiresRegulatoryReturns": str(section.requires_regulatory_returns),
                "frequencyOfReturns": section.frequency_of_returns,
                "units": ','.join(section.units),
                "timelineDate": datetime.strptime(section.timeline_date or regulation.release_date, date_format).strftime("%Y-%m-%d")
            } for section in regulation.sections
            ]
        }

        print(payload)

        # Send the API request
        response = requests.post(
            RULEBOOK_API_INVENTORY_URL,
            headers={
            'accept': 'text/plain',
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
            },
            json=payload
        )

        response.raise_for_status()  # Ensure the request was successful
        result = response.json()
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
def log_agent_request(status=None, error=None):
    try:
        token = get_token()  # Should return "Thisistokenstr"
        if token == None:
            request_auth()
            token = get_token()

        # Send the API request
        response = requests.post(
            RULEBOOK_API_AI_LOG_URL,
            headers={
            'accept': 'text/plain',
            'Authorization': f'Bearer {token}',
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

if __name__ == '__main__':
    log_agent_request(0)
    try:
        do_main()
        log_agent_request(1)
    except Exception as e:  
        log_agent_request(2, str(e))
        print(e)
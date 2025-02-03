from pydantic import BaseModel
from typing import Literal
import re
import requests
from bs4 import BeautifulSoup # type: ignore
from google.cloud import storage
import os
from google.cloud import vision_v1
from google.cloud.vision_v1 import types
from openai import OpenAI
from dotenv import load_dotenv


import pytesseract
from pdf2image import convert_from_path
from PIL import Image

load_dotenv()

llm = OpenAI(
    # api_key=os.getenv("OPENAI_API_KEY"),    
)
os.environ["GCLOUD_PROJECT"] = "eyailab"


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

  Identify the document reference number. 
  Identify the date of document. 

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
  -- Identify Title, detailed information including all instructions, references, recommendations and dates as Rule Description, Date as [date of document], all applicable Unit(s) that needs the rule and the Type.

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
    response_format=Rules
  )

  return completion.choices[0].message.parsed

if __name__ == '__main__':
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
        # with open(pdf_path, "wb") as file:
        #   content = response.content
        #   file.write(content)
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

        print(f"Title: {ref}")
        print(f"Link: {linkHref}")
        print(f"Description: {linkText}")
        print(f"Published Date: {date_str}")
        print(f"Content: {text}")
        print("------")

        circular.reference = ref
        circular.link = pdf_url
        circular.description = linkText
        circular.date = date_str
        circular.content = text

        response = extract_rules(circular)
        for rule in response.rules:
            print(f"{rule.id}: {rule.description}")


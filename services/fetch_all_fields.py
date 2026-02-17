import requests
import os
import json
from dotenv import load_dotenv
from datetime import datetime
import requests


load_dotenv()


api_token = os.getenv("API_TOKEN")
headers = {
    "Authorization" : f"{api_token}",
    "Cache-Control": "no-cache",  
    "Content-Type": "application/json",
    "Accept-Type": "application/json",
    "expand" : "teststep"
}

try:
    response = requests.get("https://qtest.gtie.dell.com/api/v3/projects/1/settings/test-cases/fields", headers=headers)
    if response.status_code == 200:
        data = response.json()
        with open('api_all_fields.json', 'w') as f:
            json.dump(data, f, indent=4)
        print(f"JSON file generated successfully: api_all_fields.json")
        print(data)
    else:
        print(f"Failed to generate JSON file. Status code: {response.status_code}")
except requests.exceptions.RequestException as e:
    print(f"Error: {e}")
        
# with open('api_all_fields.json', 'r') as f:
#     data = json.load(f)
#     for item in data:
#         if item['label'] == 'Automation Info':
#             new_data = json.dumps(item, indent=4)
#             print(new_data)
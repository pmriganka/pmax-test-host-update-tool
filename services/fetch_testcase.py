import requests
import os
import json
from dotenv import load_dotenv
from datetime import datetime



load_dotenv()

class Testcase:
    def __init__(self, auth_headers=None):
        self.test_case_output = {}
        self.auth_headers = auth_headers or {}
        
        # Fallback to environment variable if no headers provided
        if not self.auth_headers:
            self.api_token = os.getenv("API_TOKEN")
            self.headers = {
                "Authorization" : f"{self.api_token}",
                "Cache-Control": "no-cache",  
                "Content-Type": "application/json",
                "Accept-Type": "application/json",
            }
        else:
            # Use provided authentication headers
            self.headers = self.auth_headers
    

    def fetch_all_testcase_fields(self,testcase_id):
        response = requests.get(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{testcase_id}", headers=self.headers)
        data = response.json()
        return data
    
    def fetch_required_testcase_fields(self,testcase_id):
        
        data = self.fetch_all_testcase_fields(testcase_id)
        if 'web_url' in data:
            self.test_case_output['test_case_web_url'] = data['web_url']
        if 'pid' in data:
            self.test_case_output['id'] = data['pid']
        if 'name' in data:
            self.test_case_output['name'] = data['name']
        for item in data['properties']:
            if item['field_name'] == "Assigned To":
                self.test_case_output['assigned_to_value'] = item['field_value_name']
            if item['field_name'] == "Automation Developer":
                self.test_case_output['automation_developer'] = item['field_value_name']
            if item['field_name'] == "Automation Status":
                self.test_case_output['automation_status'] = item['field_value_name']
            if item['field_name'] == "Status":
                self.test_case_output['test_case_status'] = item['field_value_name']
            if item['field_name'] == "System Test Pillars":
                self.test_case_output['pillar'] = item['field_value_name'].replace('[', '').replace(']', '')
            if item['field_name'] == "Automation Target Release Date":
                # date_time_object = datetime.strptime(item['field_value'], "%Y-%m-%dT%H:%M:%S%z")
                # date_part = date_time_object.strftime("%Y-%m-%d")
                date_part = item['field_value'].split("T")[0]
                self.test_case_output['automation_release_date'] = date_part

        return self.test_case_output,data['id']
    
    def fetch_test_steps(self,testcase_id):
        test_step_fetch_response = requests.get(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{testcase_id}/test-steps", headers=self.headers)
        test_step = test_step_fetch_response.json()
        # print(json.dumps(test_step, indent=4))
        with open('services//api_test_steps.json', 'w') as f:
            json.dump(test_step, f, indent=4)
        return test_step
    
    def fetch_attachment(self,testcase_id):
        attachment_response = requests.get(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{testcase_id}/attachments", headers = self.headers)
        attachment = attachment_response.json()
        return attachment
    
    def testing(self):
        response = self.fetch_all_testcase_fields("TC-15783")
        pid = response['id']  # Access the first element of the tuple and then access the 'pid' key
        att = self.fetch_attachment(pid)
        blobid = att[0]['id']
        # response = requests.delete(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{pid}/blob-handles/{blobid}", headers=self.headers)
        #response = requests.delete(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/5038077/blob-handles/8972480", headers=self.headers)
        try:
            response = requests.delete("https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/5038077/blob-handles/8972480", headers=self.headers)
            if response.status_code == 200:
                print(f"JSON file generated successfully: api_all_fields.json")
            else:
                print(f"Failed to generate JSON file. Status code: {response}")
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")


# headers = {
#             "Authorization" : f"{os.getenv("API_TOKEN")}",
#             "Cache-Control": "no-cache",  
#             "Content-Type": "application/json",
#             "Accept-Type": "application/json",
#         }
# data = {
#   "description": "Step 4",
#   "expected": "",
#   "attachments": [
#     {
#       "name": "sample.txt",
#       "content_type": "text/plain",
#       "data": "hIuGJIOHvgl"
#     }
#   ]
# }
# tc = Testcase()
# details, id = tc.fetch_required_testcase_fields("TC-86157")
# # response = requests.post(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}/test-steps", headers = headers, json=data)
# # print(response.status_code)
# response = tc.fetch_test_steps(id)
# for i, item in enumerate(response):
#     print("Number :", i)
#     if i == 0:
#         item["description"] = "hgdfahgFDHGASDHG"
#         print(item)
#         response = requests.post(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}/test-steps/{item['id']}", headers=headers, json=item)
#     else:
#         item["description"] = ""
#         print(item)
#         # item["plain_value_text"] = ""
#         response = requests.post(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}/test-steps/{item['id']}", headers=headers, json=item)
# response = tc.fetch_test_steps(id)
# print( json.dumps(response, indent=4) )

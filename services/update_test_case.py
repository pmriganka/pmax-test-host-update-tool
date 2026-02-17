import requests
import os
import json
from dotenv import load_dotenv
from datetime import datetime
from services.fetch_testcase import Testcase
import requests
import markdown


load_dotenv()

class Updatetestcase:
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

    def fetch_status_field_value(self, field_name, type):
        with open('services\\required_automation_status.json', 'r') as file:
            data = json.load(file)
            if type == 1:
                field_value = next((item["field_value"] for item in data["Automation Status"] if item["field_value_name"] == field_name), None)
            elif type == 0:
                field_value = next((item["field_value"] for item in data["Status"] if item["field_value_name"] == field_name), None)
        return field_value

    
    def fetch_automation_developer(self, field_name):
         with open('services\\api_all_fields.json', 'r') as file:
            data = json.load(file)
            for item in data:
                if 'allowed_values' in item:
                    for value in item['allowed_values']:
                        if value['label'] == field_name and value['is_active']:
                            return value['value']
    
    def fetch_assigned_to(self, input_string):

        # input_string = input_string.replace('[', '').replace(']', '')
        names = [name.strip() for name in input_string.split(',')]   
        # Load the api_all_fields.json file into a dictionary
        with open('services\\api_all_fields.json', 'r') as f:
            data = json.load(f)
            
            # Initialize an empty list to store the field values
            field_values = []

            # Iterate over the allowed_values list in the dictionary
            for item in data:
                if item['label'] == "Assigned To":
                    for persons in item['allowed_values']:
                        if persons['label'] in names:
                            field_values.append(persons['value'])     
        # Convert the list of field values to a string
        output_string = '[' + ','.join(map(str, field_values)) + ']'
       
        return output_string              
                            
    def remove_attachments(self, testcase_id):
        try:
            fetched_data = Testcase.fetch_all_testcase_fields(self,testcase_id)
            testcaseid = fetched_data['id']
            attachments = Testcase.fetch_attachment(self,testcaseid)
            
            if not attachments:
                return {"success": True, "message": "No attachments found to remove", "deleted_count": 0}
            
            attachment_ids = [attachment["id"] for attachment in attachments]
            deleted_count = 0
            failed_count = 0
            permission_error = False
            
            for attachment in attachment_ids:
                response = requests.delete(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{testcaseid}/blob-handles/{attachment}", headers=self.headers)
                if response.status_code in [200, 204]:  # 200 OK or 204 No Content are both successful
                    deleted_count += 1
                else:
                    failed_count += 1
                    print(f"Failed to delete attachment {attachment}: {response.status_code}")
                    # Print response text for debugging
                    if response.text:
                        print(f"Response text: {response.text}")
                        # Check for specific permission errors
                        if "Access is denied" in response.text or "403" in str(response.status_code):
                            print("PERMISSION ERROR: The API token does not have permission to delete attachments.")
                            print("SOLUTION: Please contact your qTest administrator to grant attachment deletion permissions.")
                            permission_error = True
            
            return {
                "success": failed_count == 0,
                "message": f"Deleted {deleted_count} attachment(s)" if deleted_count > 0 else ("No attachments deleted - permission denied" if failed_count > 0 and permission_error else "No attachments deleted"),
                "deleted_count": deleted_count,
                "failed_count": failed_count,
                "permission_error": permission_error
            }
            
        except Exception as e:
            return {"success": False, "message": f"Error removing attachments: {str(e)}", "deleted_count": 0, "failed_count": 0}
        
    def update_attachments(self, testcase_id, filename, filedata):
        file_headers = {
            "Authorization" : f"{self.api_token}",
            "Cache-Control": "no-cache",  
            "Content-Type": "application/jpeg",
            "File-Name": f"{filename}",
            "expand" : "teststep"
        }
        fetched_data = Testcase.fetch_all_testcase_fields(self,testcase_id)
        testcaseid = fetched_data['id']
        response = requests.post(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{testcaseid}/blob-handles", headers=file_headers, data = filedata)
        return response.status_code

    def update_test_case(self, update_dict):
        response = requests.get(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{update_dict['test_case_id']}", headers=self.headers)
        data = response.json()
        for item in data['properties']:
            if item['field_name'] == "Status" and update_dict.get('test_case_status') and update_dict['test_case_status'] != "None":
                    item['field_value'] = self.fetch_status_field_value(update_dict['test_case_status'], 0)
            if item['field_name'] == "Automation Status" and update_dict.get('automation_status') and update_dict['automation_status'] != "None":
                    item['field_value'] = self.fetch_status_field_value(update_dict['automation_status'], 1)
            if item['field_name'] == "Automation Developer" and "testcase_automation_developer" in update_dict:
                    item['field_value'] = self.fetch_automation_developer(update_dict['testcase_automation_developer'])
            if item['field_name'] == "Assigned To" and "assigned_to" in update_dict:
                    item['field_value'] = self.fetch_assigned_to(update_dict['assigned_to']) 
            if item['field_name'] == "Automation Target Release Date" and "automation_target_release_date" in update_dict:
                    item['field_value'] = update_dict['automation_target_release_date']
        id = data['id']
        with open('api_single_test_case_fields.json', 'w') as f:
             json.dump(data, f, indent=4)
        response = requests.put(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}", headers=self.headers, json=data)
        

    def delete_test_steps(self, teststeps, id):
        try:
            for item in teststeps:
                response = requests.delete(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}/test-steps/{item['id']}", headers=self.headers)
        except Exception as e:
            return e
        else:
            return f"All steps have been successfully deleted. Status code : {response.status_code}"        
            

    def add_test_steps(self, testcase_id, teststeps_text):
        request_sample = {
                "description": "Step 4 updated",
                "expected": ""
                }
        
        fetched_all_tc_fields = Testcase.fetch_all_testcase_fields(self,testcase_id)
        id = fetched_all_tc_fields['id']  
        fetched_details = Testcase.fetch_test_steps(self, id)
        if fetched_details:
            for i, item in enumerate(fetched_details):
                if i == 0:
                    # Create a fresh request_sample for each iteration
                    fresh_request = {
                        "description": teststeps_text,
                        "expected": ""
                    }
                    response = requests.put(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}/test-steps/{item['id']}", headers=self.headers, json=fresh_request)
                else:
                    # Create a fresh request for clearing
                    clear_request = {
                        "description": "",
                        "expected": ""
                    }
                    response = requests.put(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}/test-steps/{item['id']}", headers=self.headers, json=clear_request)
        else:
            data = {
                        "description": "",
                        "expected": "no exception throw",
                        "attachments": [
                            {
                                "name": "sample.txt",
                                "content_type": "text/plain",
                                "data": "hIuGJIOHvgl"
                            }
                        ]
                    }
            response = requests.post(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}/test-steps", headers=self.headers, json=data)
            fetched_details = Testcase.fetch_test_steps(self, id)
            for item in fetched_details:
                fresh_request = {
                    "description": teststeps_text,
                    "expected": ""
                }
                response = requests.put(f"https://qtest.gtie.dell.com/api/v3/projects/442/test-cases/{id}/test-steps/{item['id']}", headers=self.headers, json=fresh_request)
            
         



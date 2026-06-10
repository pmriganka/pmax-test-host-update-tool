import streamlit as st
from streamlit_quill import st_quill
from services.fetch_testcase import Testcase
from services.update_test_case import Updatetestcase
from services.notification_utils import NotificationManager
from services.auth_service import get_auth_service, require_authentication
import time
import datetime
import html
import os
import re

# Authentication is required ONLY for this page. All other pages remain
# accessible without logging in. (Page config is set in streamlitapp.py.)
if not require_authentication():
    st.stop()


def apply_image_width(html_content, max_width_pct):
    """Force every <img> in the HTML to a max width (%) while keeping aspect ratio."""
    if not html_content:
        return html_content

    def _repl(match):
        tag = match.group(0)
        # Drop any hard-coded width/height attributes so the style takes over
        tag = re.sub(r'\s(width|height)="[^"]*"', '', tag)
        sizing = "max-width:{}%;height:auto;".format(max_width_pct)
        if re.search(r'style="', tag):
            tag = re.sub(
                r'style="([^"]*)"',
                lambda s: 'style="{};{}"'.format(s.group(1).rstrip(';'), sizing),
                tag,
                count=1,
            )
        else:
            tag = tag[:-1] + ' style="{}">'.format(sizing)
        return tag

    return re.sub(r'<img[^>]*>', _repl, html_content)

# Get authentication headers
auth_service = get_auth_service()
auth_headers = auth_service.get_auth_headers()

col1, col2 = st.columns([1,1], gap="large")
with col1:
    with st.form("test_case_form"):
        testcase_id = st.text_input("Test Case ID")
        testcase_status = st.radio("Test Case status", ["None" , "In Design" , "Ready to Run"])
        testcase_assignee = st.text_input("Test Case Assignee")
        testcase_automation_status = st.radio("Test Case Automation status", ["None" , "Manual - Not Automatable" , "Manual - Planning (Automatable)" ,  "Under Development" , "Release Pending" , "Released"])
        selected_date = st.date_input(label="Automation Target Release Date", value=0 or datetime.date(2022, 1, 1))

        testcase_automation_developer = st.text_input("Test Case Automation Developer" )
        uploaded_file = st.file_uploader("Attach a file", type = ["pdf", "png", "jpg", "jpeg", "txt", "csv", "log"])
        
        remove_attachment = st.checkbox('Remove Attachment')
        # testcase_steps = st.text_area(" Enter Test Steps", height=200)
        testcase_steps = st_quill(
            placeholder="Enter your test steps here...",
            html=True,
            toolbar=[
                [{"font": []}, {"size": ["small", False, "large", "huge"]}],
                ["bold", "italic", "underline", "strike"],
                [{"color": []}, {"background": []}],
                [{"list": "ordered"}, {"list": "bullet"}],
                [{"header": [1, 2, 3, 4, 5, 6, False]}],
                ["link", "image", "code-block"],
                ["clean"],
            ],
            key="testcase_steps_editor",
        )
        image_max_width = st.slider(
            "Max image width (%)",
            min_value=10,
            max_value=100,
            value=100,
            step=5,
            help="Scale embedded images/snippets in the saved test steps and the preview.",
        )
        
        form_c1 , form_c2 = st.columns(2)
        with form_c1:
            fetch = st.form_submit_button("Fetch")
        with form_c2:
            update = st.form_submit_button("Update")

with col2:
    if fetch:
        with st.spinner("Processing the fetch request...."):
            testcase = Testcase(auth_headers)
            output_dict = dict()
            if not testcase_id.startswith("TC-"):
                testcase_id = "TC-" + testcase_id
            
            #Fetch Required Fields
            output_dict,id = testcase.fetch_required_testcase_fields(testcase_id)
            fetch_test_case_steps = testcase.fetch_test_steps(id)
            attachment = testcase.fetch_attachment(id)
            
            # App Display
            st.write("        ")
            st.markdown(f"""<div><span style="color:#b6b6f2">TEST CASE ID :  </span><span>{output_dict['id']}</span></div>""", unsafe_allow_html=True)
            st.write("        ")
            st.markdown(f"""<div><span style="color:#b6b6f2">TEST CASE NAME :  </span><span>{output_dict['name']}</span></div>""", unsafe_allow_html=True)
            st.write("        ")
            st.markdown(f"""<div><span style="color:#b6b6f2">TEST CASE STATUS :  </span><span>{output_dict['test_case_status']}</span></div>""", unsafe_allow_html=True)
            st.write("        ")
            st.markdown(f"""<div><span style="color:#b6b6f2">TEST CASE ASSIGNEE :  </span><span>{output_dict['assigned_to_value'].strip("[]")}</span></div>""", unsafe_allow_html=True)
            st.write("        ")
            st.markdown(f"""<div><span style="color:#b6b6f2">TEST PILLAR :  </span><span>{output_dict['pillar']}</span></div>""", unsafe_allow_html=True)
            st.write("        ")
            st.markdown(f"""<div><span style="color:#b6b6f2">AUTOMATION STATUS :  </span><span>{output_dict['automation_status']}</span></div>""", unsafe_allow_html=True)
            st.write("        ")
            st.markdown(f"""<div><span style="color:#b6b6f2">AUTOMATION DEVELOPER :  </span><span>{output_dict['automation_developer']}</span></div>""", unsafe_allow_html=True)
            st.write("        ")
            st.markdown(f"""<div><span style="color:#b6b6f2">AUTOMATION TARGET RELEASE DATE:  </span><span>{output_dict['automation_release_date']}</span></div>""", unsafe_allow_html=True)
            st.write("        ")
            if attachment:
                # attachment = attachment[0]['links'][0]['href']
                st.markdown(f"""<div><span style="color:#b6b6f2">ATTACHMENTS:  </span>""", unsafe_allow_html=True)
                for item in attachment:
                    st.markdown(f"[{item['name']}]({item['web_url']})")
                st.write("        ")
            else:
                st.markdown("""<div><span style="color:#b6b6f2">ATTACHMENTS :  </span><span> No Attachemnt Found </span></div>""", unsafe_allow_html=True)
                st.write("       ")
            st.markdown(f"""<div><span style="color:#b6b6f2">TEST CASE STEPS :  </span></div>""", unsafe_allow_html=True)
            st.write("        ")
            if not fetch_test_case_steps:
                st.error(" No test steps Found  ")
            else:
                for step in fetch_test_case_steps:
                    # st.markdown(step['description'], unsafe_allow_html= True)
                    st.markdown(f"""<div>{apply_image_width(step['description'], image_max_width)}</div>""", unsafe_allow_html= True)

    if update:
        testcase = Updatetestcase(auth_headers)
        notifications = []
        
        # Get current test case data for comparison
        current_data = {}
        if testcase_id:
            for item in testcase_id.split(','):
                tc = item.strip()
                if not tc.startswith("TC-"):
                    tc = "TC-" + tc
                try:
                    current_data[tc] = testcase.fetch_required_testcase_fields(tc)[0]
                except:
                    current_data[tc] = {}
        
        update_dict = {}
        if not testcase_id:
            st.error("Please enter the test case id")
        else:
            for item in testcase_id.split(','):
                tc = item.strip()
                if not tc.startswith("TC-"):
                    tc = "TC-" + tc
                with st.spinner("Updating the test case ...."):
                    update_dict['test_case_id'] = tc
                    
                    # Track field changes and create notifications
                    current_fields = current_data.get(tc, {})
                    
                    if testcase_status is not None and testcase_status != "None":
                        old_status = current_fields.get('test_case_status', 'None')
                        if old_status != testcase_status:
                            update_dict['test_case_status'] = testcase_status
                            notifications.append(
                                NotificationManager.create_field_update_notification(
                                    "Test Case Status", old_status, testcase_status, tc
                                )
                            )
                    
                    if testcase_automation_status is not None and testcase_automation_status != "None":
                        old_automation = current_fields.get('automation_status', 'None')
                        if old_automation != testcase_automation_status:
                            update_dict['automation_status'] = testcase_automation_status
                            notifications.append(
                                NotificationManager.create_field_update_notification(
                                    "Automation Status", old_automation, testcase_automation_status, tc
                                )
                            )
                    
                    if testcase_automation_developer and testcase_automation_developer.strip():
                        old_developer = current_fields.get('automation_developer', '')
                        if old_developer != testcase_automation_developer:
                            update_dict['testcase_automation_developer'] = testcase_automation_developer
                            notifications.append(
                                NotificationManager.create_field_update_notification(
                                    "Automation Developer", old_developer, testcase_automation_developer, tc
                                )
                            )
                    
                    if testcase_assignee and testcase_assignee.strip():
                        old_assignee = current_fields.get('assigned_to_value', '').strip("[]")
                        if old_assignee != testcase_assignee:
                            update_dict['assigned_to'] = testcase_assignee
                            notifications.append(
                                NotificationManager.create_field_update_notification(
                                    "Assigned To", old_assignee, testcase_assignee, tc
                                )
                            )
                    
                    datetime_string = selected_date.strftime("%Y-%m-%d")
                    if datetime_string != "2022-01-01":
                        date_object = datetime.datetime.strptime(datetime_string, "%Y-%m-%d")
                        output_string = date_object.isoformat() + "+00:00"
                        old_date = current_fields.get('automation_release_date', '')
                        if old_date != output_string:
                            update_dict['automation_target_release_date'] = output_string
                            notifications.append(
                                NotificationManager.create_field_update_notification(
                                    "Target Release Date", old_date.split("T")[0] if old_date else 'None', 
                                    datetime_string, tc
                                )
                            )
                    
                    # Update test case fields first
                    if update_dict:
                        testcase.update_test_case(update_dict)

                    # Handle attachment operations
                    attachment_result = None
                    if remove_attachment:
                        with st.spinner("Removing attachments...."):
                            attachment_result = testcase.remove_attachments(tc)
                        if attachment_result['success']:
                            if attachment_result['deleted_count'] > 0:
                                notifications.append(
                                    NotificationManager.create_attachment_notification(
                                        "remove", "", "success", f"Deleted {attachment_result['deleted_count']} attachments"
                                    )
                                )
                                st.success(f"✅ {attachment_result['message']}")
                            else:
                                notifications.append(
                                    NotificationManager.create_attachment_notification(
                                        "remove", "", "info", "No attachments to remove"
                                    )
                                )
                                st.info(f"ℹ️ {attachment_result['message']}")
                        else:
                            if attachment_result.get('permission_error', False):
                                st.error("❌ Permission Denied: The API token does not have permission to delete attachments.")
                                st.warning("🔧 **Solution**: Please contact your qTest administrator to grant attachment deletion permissions to your API token.")
                                st.info("📋 **Current token permissions**: Read and update test cases only")
                                st.info("🔑 **Required permission**: Attachment deletion (blob-handles DELETE)")
                                notifications.append(
                                    NotificationManager.create_attachment_notification(
                                        "remove", "", "error", "Permission denied"
                                    )
                                )
                            else:
                                st.error(f"❌ {attachment_result['message']}")
                                notifications.append(
                                    NotificationManager.create_attachment_notification(
                                        "remove", "", "error", attachment_result['message']
                                    )
                                )
                    elif uploaded_file is not None:
                        with st.spinner("Uploading attachment...."):
                            file_name = uploaded_file.name
                            file_data = uploaded_file.read()
                            
                            # Upload the main file
                            file_upload_response = testcase.update_attachments(tc, file_name, file_data)
                            if file_upload_response in [200, 201]:  # 200 OK or 201 Created are both successful
                                st.success(f"✅ Attachment '{file_name}' uploaded successfully (Status: {file_upload_response})")
                                notifications.append(
                                    NotificationManager.create_attachment_notification(
                                        "upload", file_name, "success", "File uploaded successfully"
                                    )
                                )
                            else:
                                st.error(f"❌ Failed to upload attachment (Status: {file_upload_response})")
                                notifications.append(
                                    NotificationManager.create_attachment_notification(
                                        "upload", file_name, "error", f"Upload failed (Status: {file_upload_response})"
                                    )
                                )
                    
                    if testcase_steps:
                        with st.spinner("Updating test steps...."):
                            # Extract text content from Quill editor output
                            if isinstance(testcase_steps, dict):
                                # Quill editor returns a dict, extract the text/html content
                                steps_text = testcase_steps.get('html', '') or testcase_steps.get('text', '') or str(testcase_steps)
                            else:
                                # If it's already a string, use it directly
                                steps_text = str(testcase_steps)
                            
                            steps_text = apply_image_width(steps_text, image_max_width)
                            testcase.add_test_steps(tc, steps_text)
                            st.success("✅ Test steps updated successfully")
                            notifications.append(
                                NotificationManager.create_test_steps_notification(
                                    "updated", "success", "Test steps content updated"
                                )
                            )
                    
                    # Display notifications
                    if notifications:
                        st.divider()
                        NotificationManager.show_summary_banner(notifications)
                        NotificationManager.display_notifications(notifications, "Field Updates")
                        
                        # Store notifications for potential future use
                        NotificationManager.store_notifications(notifications)
                    


                


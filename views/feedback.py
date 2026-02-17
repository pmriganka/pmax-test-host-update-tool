import streamlit as st
import win32com.client
import pythoncom
from datetime import datetime

st.set_page_config(layout="wide")

st.title("� Feedbacks and Change Request")
st.markdown("---")

RECIPIENT_EMAIL = "Mriganka.Paul@dell.com"

def send_email(name, email, subject, description):
    """Send change request details via Outlook desktop client."""
    try:
        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch('Outlook.Application')
        mail = outlook.CreateItem(0)
        mail.To = RECIPIENT_EMAIL
        mail.Subject = f"Change Request: {subject}"
        mail.Body = (
            f"Change Request Submitted\n"
            f"========================\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Subject: {subject}\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"\nDescription:\n{description}"
        )
        mail.Send()
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        pythoncom.CoUninitialize()

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.subheader("📋 Submit Change Request")

    with st.form("change_request_form"):
        name = st.text_input(
            "Name *",
            placeholder="Enter your name",
            help="Your full name"
        )

        email = st.text_input(
            "Email *",
            value="Mriganka.Paul@dell.com"
        )

        subject = st.text_input(
            "Subject *",
            placeholder="Brief summary of the change request",
            help="A short title for your change request"
        )

        description = st.text_area(
            "Description *",
            placeholder="Describe the change request in detail...",
            height=200,
            help="Provide as much detail as possible"
        )

        submitted = st.form_submit_button("📤 Submit Change Request", use_container_width=True)

        if submitted:
            if not name.strip():
                st.error("⚠️ Please enter your name")
            elif not email.strip():
                st.error("⚠️ Please enter your email")
            elif not subject.strip():
                st.error("⚠️ Please enter a subject")
            elif not description.strip():
                st.error("⚠️ Please enter a description")
            else:
                with st.spinner("📧 Sending change request..."):
                    success, error = send_email(
                        name.strip(),
                        email.strip(),
                        subject.strip(),
                        description.strip()
                    )

                if success:
                    st.success(f"✅ Change request sent successfully to {RECIPIENT_EMAIL}")
                else:
                    st.error(f"❌ Failed to send email: {error}")
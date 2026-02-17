import streamlit as st
import os
from services.auth_service import require_authentication, get_auth_service

# Check authentication first
if not require_authentication():
    st.stop()  # Stop execution if not authenticated

#---- PAGE SETUP ----

tool_management_page = st.Page(
    page = "views/test_case_management_tool.py",
    title = "Test Case Management",
    default = True
)

vmware_interaction_page = st.Page(
    page = "views/host_interaction.py",
    title = "Host Management"
)

feedback_page = st.Page(
    page = "views/feedback.py",
    title = "Feedback & CR"
)

# Add logout button in sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 👤 User Session")

if st.sidebar.button("🚪 Logout", use_container_width=True):
    auth_service = get_auth_service()
    auth_service.logout()
    st.rerun()

# Display current session info
auth_service = get_auth_service()
if auth_service.is_authenticated():
    st.sidebar.success("✅ Authenticated")
else:
    st.sidebar.error("❌ Not Authenticated")

# Navigation
pg = st.navigation(pages = [tool_management_page, vmware_interaction_page, feedback_page])
pg.run()


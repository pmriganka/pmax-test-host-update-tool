import streamlit as st
import os
import threading
from services.auth_service import require_authentication, get_auth_service
from services.log_cleanup import cleanup_old_logs

# Run log cleanup silently in the background on app startup (only once per session)
if 'log_cleanup_done' not in st.session_state:
    threading.Thread(target=cleanup_old_logs, daemon=True).start()
    st.session_state.log_cleanup_done = True

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

system_allocation_page = st.Page(
    page = "views/system_allocation.py",
    title = "System Allocation"
)

coverage_page = st.Page(
    page = "views/coverage.py",
    title = "Coverage"
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
pg = st.navigation(pages = [tool_management_page, vmware_interaction_page, system_allocation_page, coverage_page, feedback_page])
pg.run()


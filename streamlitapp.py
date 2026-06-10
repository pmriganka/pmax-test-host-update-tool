import streamlit as st
import os
from services.log_cleanup import start_periodic_cleanup

# set_page_config MUST be the first Streamlit command in the app. Setting it
# here (the entry script) means individual pages must NOT call it again.
st.set_page_config(layout="wide")

# Start the background log-cleanup timer (runs now, then once every 1 day).
# Idempotent: only one thread runs per process regardless of reruns/sessions.
start_periodic_cleanup(interval_hours=24)

# NOTE: Authentication is intentionally NOT enforced here, so the whole app and
# all pages are available as soon as the Streamlit command is run. Login is
# required only inside the Test Case Management page
# (see views/test_case_management_tool.py).

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

# Navigation
pg = st.navigation(pages = [tool_management_page, vmware_interaction_page, system_allocation_page, coverage_page, feedback_page])
pg.run()


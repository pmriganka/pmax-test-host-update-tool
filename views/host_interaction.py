import streamlit as st
import os
import threading
import time
from datetime import datetime
from services.host_management import HostManagement, ScriptStoppedException
from services.handling_log import *
from services.log_cleanup import get_cleanup_warning
from components.log_viewer import create_log_viewer
from streamlit_autorefresh import st_autorefresh

# Page config is set once in streamlitapp.py (the app entry point).

# Centered single column form
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    with st.form("Box Configuration"):
        st.subheader("Host Configuration")
        
        boxname = st.text_input("Box Name", help="Enter the name of the box/host")
        
        # Reboot options in a compact row
        st.write("**Reboot Options:**")
        reboot_col1, reboot_col2, reboot_col3 = st.columns(3)
        with reboot_col1:
            esx_reboot = st.radio("Hosts", ["Yes", "No"], index=1, key="esx_reboot")
        with reboot_col2:
            vm_reboot = st.radio("Associated VMs", ["Yes", "No"], index=1, key="vm_reboot")
        with reboot_col3:
            remediate = st.radio("Host Remediate", ["Yes", "No"], index=1, key="remediate")
        
        hostname = st.text_input("ACLX Hostname (SOS VTOC)", help="Hostname containing ACLX DB script")
        script_name = st.text_input("Script Path (SOS VTOC)", help="Full path to script (e.g., /root/setup.sh)")
        
        # ADIOS configuration
        st.write("**ADIOS Configuration:**")
        adios_version = st.text_input("ADIOS Version", help="e.g., Redwood, Roble")
        
        adios_col1, adios_col2 = st.columns(2)
        with adios_col1:
            updateadios = st.radio("Update", ["Yes", "No"], index=1, key="updateadios")
        with adios_col2:
            ready_host = st.radio("Ready", ["Yes", "No"], index=0, key="ready_host")
        
        # Submit button with better styling
        submit = st.form_submit_button("🚀 START PROCESS", use_container_width=True)

log_placeholder = st.empty()

if submit:
    host_management_dict = {}
    if not boxname:
        st.error("⚠️ Please enter the box name")
    else:
        host_management_dict['system'] = boxname
        host_management_dict['esx_reboot'] = esx_reboot 
        host_management_dict['vm_reboot'] = vm_reboot
        host_management_dict['remediate'] = remediate
        host_management_dict['updateadios'] = updateadios
        if hostname and script_name:
            host_management_dict['hostname'] = hostname
            host_management_dict['script_name'] = script_name
        if adios_version :
            host_management_dict['adios_versions'] = adios_version
        host_management_dict['ready_host'] = "Yes"
        
        # Show configuration summary
        # with st.expander("📋 Configuration Summary", expanded=True):
        #     st.json(host_management_dict)
        
        # Execute host management in background thread with live log streaming
        hm = HostManagement()
        stop_event = threading.Event()
        st.session_state['stop_event'] = stop_event
        st.session_state['script_running'] = True
        error_holder = [None]
        stopped_holder = [False]

        def run_main():
            try:
                hm.main(host_management_dict, stop_event=stop_event)
            except ScriptStoppedException:
                stopped_holder[0] = True
            except Exception as e:
                error_holder[0] = e

        worker = threading.Thread(target=run_main, daemon=True)
        worker.start()

        # Wait briefly for the log file to be created
        time.sleep(2)

        # Find the log file for this box
        log_dir = "Logs"
        log_file_path = None
        if os.path.exists(log_dir):
            box_upper = boxname.upper()
            box_logs = [
                os.path.join(log_dir, f)
                for f in os.listdir(log_dir)
                if f.endswith(".log") and box_upper in f
            ]
            if box_logs:
                log_file_path = max(box_logs, key=os.path.getmtime)

        st.subheader("📡 Live Logs")

        # Stop button
        stop_col, status_col = st.columns([1, 4])
        with stop_col:
            stop_btn = st.button("🛑 Stop Script", key="stop_script", type="primary", use_container_width=True)
            if stop_btn:
                stop_event.set()

        log_container = st.empty()
        status_placeholder = st.empty()
        lines_read = 0

        while worker.is_alive():
            if log_file_path and os.path.exists(log_file_path):
                try:
                    with open(log_file_path, "r", encoding="utf-8") as f:
                        all_lines = f.readlines()
                    if len(all_lines) > lines_read:
                        lines_read = len(all_lines)
                        log_text = "".join(all_lines[-200:])
                        log_container.code(log_text, language=None)
                except Exception:
                    pass
            if stop_event.is_set():
                status_placeholder.warning("⏳ Stopping script...")
            else:
                status_placeholder.info("🔄 Execution in progress...")
            time.sleep(2)

        # Final read after thread finishes
        if log_file_path and os.path.exists(log_file_path):
            try:
                with open(log_file_path, "r", encoding="utf-8") as f:
                    all_lines = f.readlines()
                log_text = "".join(all_lines[-200:])
                log_container.code(log_text, language=None)
            except Exception:
                pass

        status_placeholder.empty()
        st.session_state['script_running'] = False

        if stopped_holder[0]:
            st.warning("⚠️ Script was stopped by user.")
        elif error_holder[0]:
            st.error(f"❌ Error: {error_holder[0]}")
        else:
            st.success("✅ Host management operation completed!")

        # Display cleanup warning after operations
        warning_message, cleanup_stats = get_cleanup_warning()
        if warning_message and not st.session_state.get('cleanup_snoozed', False):
            st.warning(warning_message)
            
            # Add cleanup action buttons
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🗑️ Clean Up Old Logs", key="cleanup_host", help="Delete logs older than 24 hours"):
                    from services.log_cleanup import LogCleanup
                    with st.spinner("🧹 Cleaning up old logs..."):
                        cleanup = LogCleanup()
                        results = cleanup.schedule_cleanup()
                    
                    if results['deleted_count'] > 0:
                        st.success(f"✅ Deleted {results['deleted_count']} old log files, freed {results['total_freed_mb']:.2f} MB")
                    else:
                        st.info("ℹ️ No old logs to delete")
                    
                    st.rerun()
            
            with col2:
                if st.button("⏰ Snooze Warning", key="snooze_host", help="Dismiss warning for this session"):
                    st.session_state['cleanup_snoozed'] = True
                    st.rerun()

st.divider()

# Determine the latest (ongoing) log file
live_log_dir = "Logs"
live_log_path = None
if os.path.exists(live_log_dir):
    all_logs = [
        os.path.join(live_log_dir, f)
        for f in os.listdir(live_log_dir)
        if f.endswith(".log")
    ]
    if all_logs:
        live_log_path = max(all_logs, key=os.path.getmtime)

# Live Logs Section — shows the latest running log
hdr_col, btn_col = st.columns([4, 1])
with hdr_col:
    st.subheader("📋 Live Logs")
with btn_col:
    st.write("")
    if st.button("🔄 Refresh", key="refresh_live_log"):
        st.rerun()

# Auto-refresh every 5 seconds
st_autorefresh(interval=5000, limit=None, key="live_log_autorefresh")

# Check if the latest log is still ongoing (not completed)
live_log_ongoing = False
if live_log_path and os.path.exists(live_log_path):
    try:
        with open(live_log_path, "r", encoding="utf-8") as lf:
            log_lines = lf.readlines()
        log_text = "".join(log_lines) if log_lines else ""
        # Script is still running if log doesn't contain an end marker
        if "End of Script" not in log_text and "Script Stopped by User" not in log_text and "No Details are found" not in log_text and "Script aborted due to" not in log_text:
            live_log_ongoing = True
    except Exception:
        pass

if live_log_ongoing:
    info_col, stop_col = st.columns([4, 1])
    with info_col:
        st.info(f"📡 Showing latest log: **{os.path.basename(live_log_path)}** (auto-refreshes every 5s)")
    with stop_col:
        st.write("")
        if st.button("🛑 Stop Script", key="stop_script_live", type="primary", use_container_width=True):
            if 'stop_event' in st.session_state:
                st.session_state['stop_event'].set()
                st.warning("⏳ Stop signal sent...")
    try:
        with open(live_log_path, "r", encoding="utf-8") as lf:
            log_lines = lf.readlines()
        log_text = "".join(log_lines) if log_lines else ""
        st.code(log_text, language=None)
    except Exception as e:
        st.error(f"Error reading log: {e}")
else:
    st.info("No active script running. Live logs will appear here when you start a host operation.")

# Log Management Section — excludes the ongoing/latest log
with st.expander("📂 Log Management", expanded=False):
    if os.path.exists(live_log_dir):
        now = time.time()
        log_files = []
        deleted_old = []

        for f in os.listdir(live_log_dir):
            if not f.endswith(".log"):
                continue
            file_path = os.path.join(live_log_dir, f)

            # Skip the ongoing/latest log if it's still running
            if live_log_ongoing and live_log_path and os.path.abspath(file_path) == os.path.abspath(live_log_path):
                continue

            try:
                stat = os.stat(file_path)
                age_days = (now - stat.st_mtime) / (24 * 60 * 60)

                # Auto-delete logs older than 5 days
                if age_days > 5:
                    os.remove(file_path)
                    deleted_old.append(f)
                    continue

                log_files.append({
                    'name': f,
                    'path': file_path,
                    'size': stat.st_size,
                    'modified': stat.st_mtime,
                    'modified_str': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'age_days': age_days,
                })
            except Exception:
                continue

        if deleted_old:
            st.success(f"🗑️ Auto-deleted {len(deleted_old)} log(s) older than 5 days: {', '.join(deleted_old)}")

        if log_files:
            log_files.sort(key=lambda x: x['modified'], reverse=True)

            st.caption(f"**{len(log_files)}** older log file(s) in `{live_log_dir}/`")

            for i, log_file in enumerate(log_files):
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                with col1:
                    display_name = log_file['name'] if len(log_file['name']) <= 35 else log_file['name'][:32] + "..."
                    st.text(f"📄 {display_name}")
                with col2:
                    st.text(f"📅 {log_file['modified_str']}")
                with col3:
                    size_kb = log_file['size'] / 1024
                    age_str = f"{log_file['age_days']:.1f}d ago"
                    st.text(f"💾 {size_kb:.1f}KB  ({age_str})")
                with col4:
                    if st.button("👁️", key=f"view_log_{i}", help="View log"):
                        st.session_state['selected_log'] = log_file['path']

            # Show selected log
            if 'selected_log' in st.session_state:
                sel_path = st.session_state['selected_log']
                if os.path.exists(sel_path):
                    st.divider()
                    hdr_col, close_col = st.columns([4, 1])
                    with hdr_col:
                        st.subheader(f"📋 {os.path.basename(sel_path)}")
                        create_log_viewer(sel_path, key="selected_log_viewer")
                    with close_col:
                        st.write("")
                        if st.button("❌ Close", key="close_selected_log"):
                            del st.session_state['selected_log']
                            st.rerun()
                else:
                    st.warning("Selected log file no longer exists.")
                    del st.session_state['selected_log']
        else:
            st.info("No older log files found.")
    else:
        st.warning("Logs directory not found.")
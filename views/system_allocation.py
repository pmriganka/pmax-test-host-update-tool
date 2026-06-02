import streamlit as st
import os
import threading
import time
from datetime import datetime
from services.system_allocation import SystemAllocation
from services.host_management import ScriptStoppedException
from services.log_cleanup import get_cleanup_warning
from components.log_viewer import create_log_viewer
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    with st.form("System Allocation"):
        st.subheader("System Allocation")
        boxname = st.text_input("System (Box Name)", help="Box / system name (e.g. OGSCK)")
        percentage = st.number_input(
            "Percentage Allocation (%)",
            min_value=1.0, max_value=100.0, value=50.0, step=1.0,
            help="Drive every SRP's Physical-Used % to this target, then run IO 5 more minutes."
        )
        submit = st.form_submit_button("🚀 START ALLOCATION", use_container_width=True)

if submit:
    if not boxname:
        st.error("⚠️ Please enter the system / box name.")
    else:
        params = {"system": boxname, "percentage": float(percentage)}

        sa = SystemAllocation()
        stop_event = threading.Event()
        st.session_state['stop_event'] = stop_event
        st.session_state['script_running'] = True
        error_holder = [None]
        stopped_holder = [False]

        def run_main():
            try:
                sa.main(params, stop_event=stop_event)
            except ScriptStoppedException:
                stopped_holder[0] = True
            except Exception as e:
                error_holder[0] = e

        worker = threading.Thread(target=run_main, daemon=True)
        worker.start()

        # Wait briefly for the log file to be created
        time.sleep(2)

        # Find this run's log file
        log_dir = "Logs"
        log_file_path = None
        if os.path.exists(log_dir):
            box_upper = boxname.upper()
            candidates = [
                os.path.join(log_dir, f)
                for f in os.listdir(log_dir)
                if f.startswith("OGSCK_system_allocation_log_") and box_upper in f and f.endswith(".log")
            ]
            if candidates:
                log_file_path = max(candidates, key=os.path.getmtime)

        st.subheader("📡 Live Logs")

        stop_col, status_col = st.columns([1, 4])
        with stop_col:
            stop_btn = st.button("🛑 Stop Script", key="stop_script_sa", type="primary", use_container_width=True)
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
                        log_text = "".join(all_lines[-300:])
                        log_container.code(log_text, language=None)
                except Exception:
                    pass
            if stop_event.is_set():
                status_placeholder.warning("⏳ Stopping script...")
            else:
                status_placeholder.info("🔄 Execution in progress...")
            time.sleep(2)

        if log_file_path and os.path.exists(log_file_path):
            try:
                with open(log_file_path, "r", encoding="utf-8") as f:
                    all_lines = f.readlines()
                log_text = "".join(all_lines[-300:])
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
            st.success("✅ System allocation operation completed!")

        warning_message, cleanup_stats = get_cleanup_warning()
        if warning_message and not st.session_state.get('cleanup_snoozed', False):
            st.warning(warning_message)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🗑️ Clean Up Old Logs", key="cleanup_sa"):
                    from services.log_cleanup import LogCleanup
                    with st.spinner("🧹 Cleaning up old logs..."):
                        results = LogCleanup().schedule_cleanup()
                    if results['deleted_count'] > 0:
                        st.success(f"✅ Deleted {results['deleted_count']} old log files, freed {results['total_freed_mb']:.2f} MB")
                    else:
                        st.info("ℹ️ No old logs to delete")
                    st.rerun()
            with c2:
                if st.button("⏰ Snooze Warning", key="snooze_sa"):
                    st.session_state['cleanup_snoozed'] = True
                    st.rerun()

st.divider()

# ----- live log of the latest run (mirrors host_interaction layout) -----
live_log_dir = "Logs"
live_log_path = None
if os.path.exists(live_log_dir):
    sa_logs = [
        os.path.join(live_log_dir, f)
        for f in os.listdir(live_log_dir)
        if f.startswith("OGSCK_system_allocation_log_") and f.endswith(".log")
    ]
    if sa_logs:
        live_log_path = max(sa_logs, key=os.path.getmtime)

hdr_col, btn_col = st.columns([4, 1])
with hdr_col:
    st.subheader("📋 Live Logs")
with btn_col:
    st.write("")
    if st.button("🔄 Refresh", key="refresh_sa_log"):
        st.rerun()

st_autorefresh(interval=5000, limit=None, key="sa_live_log_autorefresh")

live_log_ongoing = False
if live_log_path and os.path.exists(live_log_path):
    try:
        with open(live_log_path, "r", encoding="utf-8") as lf:
            log_text = lf.read()
        if (
            "End of Script" not in log_text
            and "Script Stopped by User" not in log_text
            and "No Details are found" not in log_text
            and "Script aborted due to" not in log_text
        ):
            live_log_ongoing = True
    except Exception:
        pass

if live_log_ongoing:
    info_col, stop_col = st.columns([4, 1])
    with info_col:
        st.info(f"📡 Showing latest log: **{os.path.basename(live_log_path)}** (auto-refresh 5s)")
    with stop_col:
        st.write("")
        if st.button("🛑 Stop Script", key="stop_sa_live", type="primary", use_container_width=True):
            if 'stop_event' in st.session_state:
                st.session_state['stop_event'].set()
                st.warning("⏳ Stop signal sent...")
    try:
        with open(live_log_path, "r", encoding="utf-8") as lf:
            log_text = lf.read()
        st.code(log_text, language=None, height=700)
    except Exception as e:
        st.error(f"Error reading log: {e}")
else:
    st.info("No active system-allocation script running.")

# ----- log management (auto-deletes >5 days) -----
with st.expander("📂 Log Management", expanded=False):
    if os.path.exists(live_log_dir):
        now = time.time()
        log_files = []
        deleted_old = []
        for f in os.listdir(live_log_dir):
            if not (f.startswith("OGSCK_system_allocation_log_") and f.endswith(".log")):
                continue
            file_path = os.path.join(live_log_dir, f)
            if live_log_ongoing and live_log_path and os.path.abspath(file_path) == os.path.abspath(live_log_path):
                continue
            try:
                stat = os.stat(file_path)
                age_days = (now - stat.st_mtime) / (24 * 60 * 60)
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
            st.caption(f"**{len(log_files)}** older system-allocation log file(s) in `{live_log_dir}/`")
            for i, lf in enumerate(log_files):
                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                with c1:
                    name = lf['name'] if len(lf['name']) <= 45 else lf['name'][:42] + "..."
                    st.text(f"📄 {name}")
                with c2:
                    st.text(f"📅 {lf['modified_str']}")
                with c3:
                    size_kb = lf['size'] / 1024
                    st.text(f"💾 {size_kb:.1f}KB  ({lf['age_days']:.1f}d ago)")
                with c4:
                    if st.button("👁️", key=f"view_sa_log_{i}", help="View log"):
                        st.session_state['selected_sa_log'] = lf['path']

            if 'selected_sa_log' in st.session_state:
                sel_path = st.session_state['selected_sa_log']
                if os.path.exists(sel_path):
                    st.divider()
                    h, cc = st.columns([4, 1])
                    with h:
                        st.subheader(f"📋 {os.path.basename(sel_path)}")
                        create_log_viewer(sel_path, key="selected_sa_log_viewer")
                    with cc:
                        st.write("")
                        if st.button("❌ Close", key="close_selected_sa_log"):
                            del st.session_state['selected_sa_log']
                            st.rerun()
                else:
                    st.warning("Selected log file no longer exists.")
                    del st.session_state['selected_sa_log']
        else:
            st.info("No older system-allocation log files found.")
    else:
        st.warning("Logs directory not found.")

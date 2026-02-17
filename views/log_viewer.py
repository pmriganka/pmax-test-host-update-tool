import streamlit as st
import os
from datetime import datetime
from services.handling_log import get_latest_log, get_log_stats
from services.log_cleanup import LogCleanup, get_cleanup_warning
from components.log_viewer import create_log_viewer, display_latest_log

st.set_page_config(layout="wide")

st.title("📋 Log Viewer Dashboard")
st.markdown("---")

# Display cleanup warning at the top
warning_message, cleanup_stats = get_cleanup_warning()
if warning_message:
    st.warning(warning_message)
    
    # Add cleanup action buttons
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("🗑️ Clean Up Now", key="cleanup_now", help="Delete logs older than 24 hours"):
            with st.spinner("🧹 Cleaning up old logs..."):
                cleanup = LogCleanup()
                results = cleanup.schedule_cleanup()
            
            if results['deleted_count'] > 0:
                st.success(f"✅ Successfully deleted {results['deleted_count']} log files, freed {results['total_freed_mb']:.2f} MB")
            else:
                st.info("ℹ️ No old logs to delete")
            
            if results['failed_count'] > 0:
                st.error(f"❌ Failed to delete {results['failed_count']} log files")
            
            st.rerun()
    
    with col2:
        if st.button("📊 View Details", key="view_old_logs"):
            st.session_state['show_old_logs'] = not st.session_state.get('show_old_logs', False)
    
    with col3:
        if st.button("⏰ Snooze", key="snooze_cleanup", help="Dismiss warning for this session"):
            st.session_state['cleanup_snoozed'] = True
            st.rerun()

# Show old logs details if requested
if st.session_state.get('show_old_logs', False):
    with st.expander("📋 Old Logs Details (24+ hours)", expanded=True):
        cleanup = LogCleanup()
        old_logs = cleanup.get_old_logs()
        
        if old_logs:
            for log in old_logs:
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                
                with col1:
                    st.text(f"📄 {log['name']}")
                
                with col2:
                    st.text(f"🕐 {log['age_hours']:.1f} hours old")
                
                with col3:
                    st.text(f"💾 {log['size_mb']:.2f} MB")
                
                with col4:
                    if st.button("🗑️", key=f"delete_{log['name']}", help="Delete this log"):
                        try:
                            os.remove(log['path'])
                            st.success(f"Deleted {log['name']}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete: {str(e)}")
        else:
            st.info("No old logs found.")

# Add sidebar for navigation and controls
with st.sidebar:
    st.header("🔧 Log Controls")
    
    # Quick actions
    if st.button("🔄 Refresh All", key="refresh_all"):
        if 'selected_log' in st.session_state:
            del st.session_state['selected_log']
        st.rerun()
    
    # Log cleanup section
    st.subheader("🗑️ Cleanup Status")
    cleanup = LogCleanup()
    stats = cleanup.get_cleanup_stats()
    
    if stats['old_logs_count'] > 0:
        st.warning(f"⚠️ {stats['old_logs_count']} old logs")
        st.caption(f"📊 {stats['total_size_mb']:.2f} MB to delete")
        st.caption(f"🕐 Oldest: {stats['oldest_age_hours']:.1f} hours")
    else:
        st.success("✅ All logs recent")
        st.caption("📊 No cleanup needed")
    
    # Log statistics
    st.subheader("📊 Statistics")
    log_dir = "Logs"
    if os.path.exists(log_dir):
        log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
        st.metric("Total Log Files", len(log_files))
        
        if log_files:
            # Calculate total size
            total_size = 0
            for f in log_files:
                try:
                    total_size += os.path.getsize(os.path.join(log_dir, f))
                except:
                    continue
            
            total_size_mb = total_size / (1024 * 1024)
            st.metric("Total Size", f"{total_size_mb:.2f} MB")
            
            # Latest log info
            latest_log = get_latest_log()
            if latest_log:
                stats = get_log_stats(latest_log)
                if stats:
                    latest_size_mb = stats['size'] / (1024 * 1024)
                    st.metric("Latest Log Size", f"{latest_size_mb:.2f} MB")
    else:
        st.warning("Logs directory not found")

# Main content area
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🔴 Live Log Monitoring")
    
    # Log file selector
    log_dir = "Logs"
    if os.path.exists(log_dir):
        log_files = []
        for f in os.listdir(log_dir):
            if f.endswith(".log"):
                file_path = os.path.join(log_dir, f)
                try:
                    stat = os.stat(file_path)
                    log_files.append({
                        'name': f,
                        'path': file_path,
                        'modified': stat.st_mtime,
                        'modified_str': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
                except:
                    continue
        
        if log_files:
            # Sort by modification time (newest first)
            log_files.sort(key=lambda x: x['modified'], reverse=True)
            
            # Create dropdown for log selection
            log_options = [f"{log['name']} ({log['modified_str']})" for log in log_files]
            selected_index = st.selectbox(
                "Select Log File to Monitor:",
                range(len(log_options)),
                format_func=lambda x: log_options[x],
                index=0
            )
            
            selected_log_path = log_files[selected_index]['path']
            
            # Display log viewer
            create_log_viewer(selected_log_path, key="main_log_viewer")
        else:
            st.warning("No log files found.")
    else:
        st.error("Logs directory not found.")

with col2:
    st.subheader("📄 Log History & Analysis")
    
    # Log file list with details
    if os.path.exists(log_dir):
        log_files = []
        for f in os.listdir(log_dir):
            if f.endswith(".log"):
                file_path = os.path.join(log_dir, f)
                try:
                    stat = os.stat(file_path)
                    log_files.append({
                        'name': f,
                        'path': file_path,
                        'size': stat.st_size,
                        'modified': stat.st_mtime,
                        'modified_str': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
                except:
                    continue
        
        if log_files:
            # Sort by modification time (newest first)
            log_files.sort(key=lambda x: x['modified'], reverse=True)
            
            # Create expandable sections for log files
            for i, log_file in enumerate(log_files[:20]):  # Show top 20
                with st.expander(f"📄 {log_file['name']}"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Modified", log_file['modified_str'])
                    
                    with col2:
                        size_mb = log_file['size'] / (1024 * 1024)
                        st.metric("Size", f"{size_mb:.2f} MB")
                    
                    with col3:
                        stats = get_log_stats(log_file['path'])
                        if stats:
                            st.metric("Lines", stats['lines'])
                    
                    # Action buttons
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("👁️ View", key=f"view_{i}"):
                            st.session_state['selected_log'] = log_file['path']
                            st.rerun()
                    
                    with col2:
                        if st.button("📥 Download", key=f"download_{i}"):
                            try:
                                with open(log_file['path'], 'r', encoding='utf-8') as f:
                                    st.download_button(
                                        label="💾 Download Log",
                                        data=f.read(),
                                        file_name=log_file['name'],
                                        mime="text/plain"
                                    )
                            except Exception as e:
                                st.error(f"Error reading file: {str(e)}")
                    
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_{i}"):
                            try:
                                os.remove(log_file['path'])
                                st.success(f"Deleted {log_file['name']}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error deleting file: {str(e)}")
        else:
            st.info("No log files found.")
    else:
        st.warning("Logs directory not found.")

# Bottom section for selected log viewing
if 'selected_log' in st.session_state:
    st.divider()
    st.subheader(f"📋 Viewing: {os.path.basename(st.session_state['selected_log'])}")
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        try:
            create_log_viewer(st.session_state['selected_log'], key="selected_log_viewer")
        except Exception as e:
            st.error(f"Error creating log viewer: {str(e)}")
    
    with col2:
        st.write("**Actions:**")
        if st.button("❌ Close Viewer", key="close_selected"):
            del st.session_state['selected_log']
            st.rerun()
        
        # Show file info
        try:
            stats = get_log_stats(st.session_state['selected_log'])
            if stats:
                st.write("**File Info:**")
                st.write(f"Lines: {stats['lines']}")
                size_mb = stats['size'] / (1024 * 1024)
                st.write(f"Size: {size_mb:.2f} MB")
        except Exception as e:
            st.error(f"Error getting stats: {str(e)}")

# Footer with additional information
st.divider()
col1, col2, col3 = st.columns(3)

with col1:
    st.caption("📡 **Live Monitoring**: Real-time log updates as they are written")

with col2:
    st.caption("🔍 **Search & Filter**: Filter logs by level and search for specific content")

with col3:
    st.caption("📥 **Export**: Download logs for offline analysis")

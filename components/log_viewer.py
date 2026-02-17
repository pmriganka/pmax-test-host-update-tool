import streamlit as st
import time
from datetime import datetime
import os
from services.handling_log import get_latest_log, start_log_monitor, get_log_stats


class LogViewer:
    def __init__(self):
        self.log_placeholder = None
        self.stop_event = None
        self.log_queue = None
        self.log_lines = []
        self.max_lines = 1000  # Maximum lines to keep in memory
        
    def display_log_viewer(self, log_file_path=None, auto_refresh=True, component_key="default"):
        """
        Display a live log viewer component.
        
        Args:
            log_file_path: Path to log file. If None, will use latest log.
            auto_refresh: Whether to automatically refresh the log display.
            component_key: Unique key for this component instance.
        """
        # Get latest log if no specific file provided
        if not log_file_path:
            log_file_path = get_latest_log()
        
        if not log_file_path:
            st.warning("No log file found.")
            return
        
        if not os.path.exists(log_file_path):
            st.warning(f"Log file not found: {log_file_path}")
            return
        
        # Store the current log file path
        self.current_log_file = log_file_path
        
        # Load existing logs from the specific file (load all lines for full view)
        self._load_existing_logs(log_file_path, max_lines=None)
        
        # Display log file info
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.caption(f"📄 **Log File:** `{os.path.basename(log_file_path)}`")
        
        with col2:
            stats = get_log_stats(log_file_path)
            if stats:
                st.caption(f"📊 **Lines:** {stats['lines']}")
        
        with col3:
            if stats:
                size_mb = stats['size'] / (1024 * 1024)
                st.caption(f"💾 **Size:** {size_mb:.2f} MB")
        
        # Control buttons
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        
        with col1:
            if st.button("🔄 Refresh", key=f"refresh_log_{component_key}"):
                self._load_existing_logs(log_file_path, max_lines=None)
        
        with col2:
            if st.button("⏸️ Pause", key=f"pause_log_{component_key}", disabled=not auto_refresh):
                auto_refresh = False
                if self.stop_event:
                    self.stop_event.set()
        
        with col3:
            if st.button("▶️ Resume", key=f"resume_log_{component_key}", disabled=auto_refresh):
                auto_refresh = True
                self._start_monitoring(log_file_path)
        
        with col4:
            if st.button("🗑️ Clear", key=f"clear_log_{component_key}"):
                self.log_lines = []
        
        # Log level filter
        log_level = st.selectbox(
            "Filter by Log Level:",
            ["ALL", "INFO", "WARNING", "ERROR"],
            index=0,
            key=f"log_level_filter_{component_key}"
        )
        
        # Auto-scroll toggle
        auto_scroll = st.checkbox("📍 Auto-scroll to latest", value=True, key=f"auto_scroll_{component_key}")
        
        # Create log display area
        self.log_placeholder = st.empty()
        
        # Initialize monitoring if needed
        if auto_refresh and not self.stop_event:
            self._start_monitoring(log_file_path)
        
        # Display logs
        self._display_logs(log_level, auto_scroll, component_key)
        
        # Update logs if auto-refresh is enabled
        if auto_refresh and self.log_queue:
            self._update_logs(log_level, auto_scroll, component_key)
    
    def _start_monitoring(self, log_file_path):
        """Start monitoring the log file for new entries."""
        if self.stop_event:
            self.stop_event.set()
        
        self.stop_event, self.log_queue = start_log_monitor(log_file_path)
    
    def _load_existing_logs(self, log_file_path, max_lines=None):
        """Load existing log lines from the file."""
        try:
            with open(log_file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                # If max_lines is None, load all lines; otherwise get last max_lines
                if max_lines is None:
                    self.log_lines = [line.strip() for line in lines]
                else:
                    self.log_lines = [line.strip() for line in lines[-max_lines:]]
        except Exception as e:
            st.error(f"Error loading log file: {str(e)}")
    
    def _update_logs(self, log_level_filter, auto_scroll, component_key):
        """Update logs with new entries from the queue."""
        if not self.log_queue:
            return
        
        # Get new log entries
        new_lines = []
        while not self.log_queue.empty():
            try:
                line = self.log_queue.get_nowait()
                new_lines.append(line)
            except:
                break
        
        if new_lines:
            self.log_lines.extend(new_lines)
            # Keep only the last max_lines
            if len(self.log_lines) > self.max_lines:
                self.log_lines = self.log_lines[-self.max_lines:]
            
            self._display_logs(log_level_filter, auto_scroll, component_key)
    
    def _display_logs(self, log_level_filter, auto_scroll, component_key):
        """Display the log lines with formatting."""
        if not self.log_lines:
            # Load existing logs if none loaded (use current log file if available)
            if hasattr(self, 'current_log_file') and self.current_log_file:
                self._load_existing_logs(self.current_log_file, max_lines=None)
            else:
                latest_log = get_latest_log()
                if latest_log:
                    self._load_existing_logs(latest_log, max_lines=None)
        
        if not self.log_lines:
            self.log_placeholder.info("No log entries to display.")
            return
        
        # Filter logs by level
        filtered_lines = self._filter_logs(self.log_lines, log_level_filter)
        
        if not filtered_lines:
            self.log_placeholder.info(f"No {log_level_filter} log entries found.")
            return
        
        # Format log lines with colors
        formatted_lines = []
        for line in filtered_lines:
            formatted_line = self._format_log_line(line)
            formatted_lines.append(formatted_line)
        
        # Display in a scrollable container
        log_content = "\n".join(formatted_lines)
        
        if auto_scroll:
            # Use st.code with auto-scroll behavior
            self.log_placeholder.code(log_content, language=None, height=400)
        else:
            # Use st.markdown for static display
            self.log_placeholder.markdown(f"```\n{log_content}\n```")
    
    def _filter_logs(self, lines, log_level):
        """Filter log lines by log level."""
        if log_level == "ALL":
            return lines
        
        filtered = []
        for line in lines:
            if log_level in line:
                filtered.append(line)
        
        return filtered
    
    def _format_log_line(self, line):
        """Format a log line with appropriate colors and styling."""
        if not line:
            return ""
        
        # Extract timestamp, level, and message
        parts = line.split(" - ", 2)
        if len(parts) >= 3:
            timestamp, level, message = parts[0], parts[1], parts[2]
            
            # Color code based on log level
            if "ERROR" in level:
                return f"🔴 {timestamp} - **{level}** - {message}"
            elif "WARNING" in level:
                return f"🟡 {timestamp} - **{level}** - {message}"
            elif "INFO" in level:
                return f"🟢 {timestamp} - {level} - {message}"
            else:
                return f"🔵 {timestamp} - {level} - {message}"
        else:
            return line
    
    def stop_monitoring(self):
        """Stop the log monitoring."""
        if self.stop_event:
            self.stop_event.set()
            self.stop_event = None
        self.log_queue = None


def create_log_viewer(log_file_path=None, key="default"):
    """
    Convenience function to create a log viewer.
    
    Args:
        log_file_path: Path to log file. If None, will use latest log.
        key: Unique key for the component.
    """
    if f'log_viewer_{key}' not in st.session_state:
        st.session_state[f'log_viewer_{key}'] = LogViewer()
    
    viewer = st.session_state[f'log_viewer_{key}']
    viewer.display_log_viewer(log_file_path, component_key=key)


def display_latest_log():
    """Display the latest log file in a simple format."""
    latest_log = get_latest_log()
    if not latest_log:
        st.info("No log files found.")
        return
    
    st.subheader(f"📋 Latest Log: {os.path.basename(latest_log)}")
    
    try:
        with open(latest_log, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            # Show last 50 lines
            recent_lines = lines[-50:]
            log_content = "".join(recent_lines)
            st.code(log_content, language=None)
    except Exception as e:
        st.error(f"Error reading log file: {str(e)}")

import streamlit as st
from typing import Dict, Any, List
from datetime import datetime

class NotificationManager:
    """Manages notifications for test case field updates"""
    
    @staticmethod
    def create_field_update_notification(
        field_name: str, 
        old_value: Any = None, 
        new_value: Any = None,
        test_case_id: str = ""
    ) -> Dict[str, Any]:
        """Create a notification for field update"""
        return {
            'type': 'field_update',
            'field_name': field_name,
            'old_value': old_value,
            'new_value': new_value,
            'test_case_id': test_case_id,
            'timestamp': datetime.now(),
            'message': f"Updated {field_name}: {NotificationManager._format_value_change(old_value, new_value)}"
        }
    
    @staticmethod
    def _format_value_change(old_val: Any, new_val: Any) -> str:
        """Format the value change for display"""
        if old_val is None and new_val is not None:
            return f"Set to '{new_val}'"
        elif old_val is not None and new_val is None:
            return f"Cleared (was '{old_val}')"
        elif old_val == new_val:
            return f"No change ('{new_val}')"
        else:
            return f"'{old_val}' → '{new_val}'"
    
    @staticmethod
    def display_notifications(notifications: List[Dict[str, Any]], title: str = "Update Summary"):
        """Display notifications in Streamlit"""
        if not notifications:
            return
        
        st.subheader(f"📋 {title}")
        
        for notification in notifications:
            if notification['type'] == 'field_update':
                NotificationManager._display_field_notification(notification)
            elif notification['type'] == 'attachment':
                NotificationManager._display_attachment_notification(notification)
            elif notification['type'] == 'test_steps':
                NotificationManager._display_test_steps_notification(notification)
    
    @staticmethod
    def _display_field_notification(notification: Dict[str, Any]):
        """Display a single field update notification"""
        field_name = notification['field_name']
        old_val = notification['old_value']
        new_val = notification['new_value']
        test_case_id = notification['test_case_id']
        
        # Determine icon based on field type
        icon = NotificationManager._get_field_icon(field_name)
        
        # Create expandable section for details
        with st.expander(f"{icon} {field_name}", expanded=True):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                if old_val is not None and new_val is not None and old_val != new_val:
                    st.write("**From:**")
                    st.code(str(old_val), language=None)
                    st.write("**To:**")
                    st.code(str(new_val), language=None)
                elif old_val is None and new_val is not None:
                    st.write("**Set to:**")
                    st.code(str(new_val), language=None)
                elif new_val is None and old_val is not None:
                    st.write("**Cleared:**")
                    st.code(f"Was: {old_val}", language=None)
                else:
                    st.write("**No change:**")
                    st.code(str(new_val), language=None)
            
            with col2:
                st.write(f"**Test Case:** `{test_case_id}`")
                st.write(f"**Time:** {notification['timestamp'].strftime('%H:%M:%S')}")
    
    @staticmethod
    def _display_attachment_notification(notification: Dict[str, Any]):
        """Display attachment operation notification"""
        action = notification.get('action', 'unknown')
        filename = notification.get('filename', 'unknown')
        status = notification.get('status', 'unknown')
        
        if action == 'upload':
            icon = "📎"
            message = f"Uploaded attachment: {filename}"
        elif action == 'remove':
            icon = "🗑️"
            message = f"Removed attachments"
        else:
            icon = "📎"
            message = f"Attachment operation: {action}"
        
        if status == 'success':
            st.success(f"{icon} {message}")
        elif status == 'error':
            st.error(f"{icon} {message}")
        else:
            st.info(f"{icon} {message}")
    
    @staticmethod
    def _display_test_steps_notification(notification: Dict[str, Any]):
        """Display test steps update notification"""
        action = notification.get('action', 'updated')
        status = notification.get('status', 'success')
        
        icon = "📝"
        message = f"Test steps {action}"
        
        if status == 'success':
            st.success(f"{icon} {message}")
        else:
            st.error(f"{icon} {message}")
    
    @staticmethod
    def _get_field_icon(field_name: str) -> str:
        """Get appropriate icon for field type"""
        field_icons = {
            'test_case_status': '📊',
            'assigned_to': '👤',
            'automation_status': '🤖',
            'automation_developer': '👨‍💻',
            'automation_target_release_date': '📅',
            'testcase_automation_developer': '👨‍💻',
            'assigned_to': '👤',
            'test_case_status': '📊',
            'automation_status': '🤖'
        }
        
        # Return icon if found, otherwise default
        return field_icons.get(field_name.lower(), '📝')
    
    @staticmethod
    def create_attachment_notification(
        action: str,
        filename: str = "",
        status: str = "success",
        details: str = ""
    ) -> Dict[str, Any]:
        """Create attachment operation notification"""
        return {
            'type': 'attachment',
            'action': action,
            'filename': filename,
            'status': status,
            'details': details,
            'timestamp': datetime.now()
        }
    
    @staticmethod
    def create_test_steps_notification(
        action: str = "updated",
        status: str = "success",
        details: str = ""
    ) -> Dict[str, Any]:
        """Create test steps operation notification"""
        return {
            'type': 'test_steps',
            'action': action,
            'status': status,
            'details': details,
            'timestamp': datetime.now()
        }
    
    @staticmethod
    def show_summary_banner(notifications: List[Dict[str, Any]]):
        """Show a summary banner of all notifications"""
        if not notifications:
            return
        
        # Count notification types
        field_updates = len([n for n in notifications if n['type'] == 'field_update'])
        attachments = len([n for n in notifications if n['type'] == 'attachment'])
        test_steps = len([n for n in notifications if n['type'] == 'test_steps'])
        
        # Create summary message
        summary_parts = []
        if field_updates > 0:
            summary_parts.append(f"{field_updates} field{'s' if field_updates > 1 else ''}")
        if attachments > 0:
            summary_parts.append(f"{attachments} attachment{'s' if attachments > 1 else ''}")
        if test_steps > 0:
            summary_parts.append(f"{test_steps} test step{'s' if test_steps > 1 else ''}")
        
        if summary_parts:
            summary = ", ".join(summary_parts)
            st.info(f"📋 **Update Summary:** {summary} updated successfully")
    
    @staticmethod
    def store_notifications(notifications: List[Dict[str, Any]], key: str = "last_notifications"):
        """Store notifications in session state"""
        st.session_state[key] = notifications
    
    @staticmethod
    def get_stored_notifications(key: str = "last_notifications") -> List[Dict[str, Any]]:
        """Get stored notifications from session state"""
        return st.session_state.get(key, [])

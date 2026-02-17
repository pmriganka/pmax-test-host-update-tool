import os
import time
from datetime import datetime, timedelta
import logging

class LogCleanup:
    def __init__(self, log_dir="Logs"):
        self.log_dir = log_dir
        self.max_age_hours = 24  # Delete logs older than 24 hours
        
    def get_log_age_hours(self, file_path):
        """Get the age of a log file in hours."""
        try:
            file_mtime = os.path.getmtime(file_path)
            file_time = datetime.fromtimestamp(file_mtime)
            current_time = datetime.now()
            age = current_time - file_time
            return age.total_seconds() / 3600  # Convert to hours
        except Exception:
            return 0
    
    def get_old_logs(self):
        """Get list of log files older than 24 hours."""
        old_logs = []
        
        if not os.path.exists(self.log_dir):
            return old_logs
            
        for filename in os.listdir(self.log_dir):
            if filename.endswith(".log"):
                file_path = os.path.join(self.log_dir, filename)
                age_hours = self.get_log_age_hours(file_path)
                
                if age_hours > self.max_age_hours:
                    old_logs.append({
                        'name': filename,
                        'path': file_path,
                        'age_hours': age_hours,
                        'size_mb': os.path.getsize(file_path) / (1024 * 1024)
                    })
        
        return sorted(old_logs, key=lambda x: x['age_hours'], reverse=True)
    
    def delete_old_logs(self):
        """Delete log files older than 24 hours."""
        deleted_logs = []
        failed_deletions = []
        
        old_logs = self.get_old_logs()
        
        for log_info in old_logs:
            try:
                os.remove(log_info['path'])
                deleted_logs.append(log_info)
                logging.info(f"Deleted old log file: {log_info['name']} (Age: {log_info['age_hours']:.1f} hours)")
            except Exception as e:
                failed_deletions.append({'log': log_info, 'error': str(e)})
                logging.error(f"Failed to delete log file {log_info['name']}: {str(e)}")
        
        return deleted_logs, failed_deletions
    
    def get_cleanup_stats(self):
        """Get statistics about log cleanup."""
        old_logs = self.get_old_logs()
        
        total_size_mb = sum(log['size_mb'] for log in old_logs)
        oldest_age = max([log['age_hours'] for log in old_logs]) if old_logs else 0
        
        return {
            'old_logs_count': len(old_logs),
            'total_size_mb': total_size_mb,
            'oldest_age_hours': oldest_age,
            'max_age_hours': self.max_age_hours
        }
    
    def display_cleanup_warning(self):
        """Display a warning about old logs that will be deleted."""
        stats = self.get_cleanup_stats()
        
        if stats['old_logs_count'] > 0:
            # Create warning message
            warning_message = f"""
            ⚠️ **CAUTION: Log Cleanup Required**
            
            📊 **Found {stats['old_logs_count']} log file(s) older than 24 hours**
            💾 **Total size to be deleted: {stats['total_size_mb']:.2f} MB**
            🕐 **Oldest log: {stats['oldest_age_hours']:.1f} hours old**
            
            🗑️ **These logs will be automatically deleted to save space.**
            """
            
            return warning_message, stats
        else:
            return None, stats
    
    def schedule_cleanup(self):
        """Perform the cleanup and return results."""
        deleted_logs, failed_deletions = self.delete_old_logs()
        
        return {
            'deleted_count': len(deleted_logs),
            'failed_count': len(failed_deletions),
            'deleted_logs': deleted_logs,
            'failed_deletions': failed_deletions,
            'total_freed_mb': sum(log['size_mb'] for log in deleted_logs)
        }


def cleanup_old_logs():
    """Convenience function to perform log cleanup."""
    cleanup = LogCleanup()
    return cleanup.schedule_cleanup()


def get_cleanup_warning():
    """Convenience function to get cleanup warning."""
    cleanup = LogCleanup()
    return cleanup.display_cleanup_warning()

import os 
import time
from threading import Thread, Event
from queue import Queue


def get_latest_log():

    LOG_DIR = "Logs"
    logs = []

    for f in os.listdir(LOG_DIR):
        if f.endswith(".log"):
            logs.append(os.path.join(LOG_DIR, f))

    if logs:
        return max( logs, key=os.path.getmtime)
    else:
        return None
    

def live_log(log_file_path, stop_event, log_queue):
    """
    Generator function that yields new log lines from the specified log file.
    Runs in a separate thread and puts new lines into a queue.
    """
    if not log_file_path or not os.path.exists(log_file_path):
        return
    
    try:
        with open(log_file_path, 'r', encoding='utf-8') as file:
            # Go to end of file
            file.seek(0, 2)
            
            while not stop_event.is_set():
                line = file.readline()
                if line:
                    log_queue.put(line.strip())
                else:
                    time.sleep(0.1)  # Small delay to prevent busy waiting
                    
    except Exception as e:
        log_queue.put(f"Error reading log file: {str(e)}")


def start_log_monitor(log_file_path):
    """
    Start monitoring a log file in a separate thread.
    Returns the stop event and queue for communication.
    """
    stop_event = Event()
    log_queue = Queue()
    
    thread = Thread(target=live_log, args=(log_file_path, stop_event, log_queue))
    thread.daemon = True
    thread.start()
    
    return stop_event, log_queue


def get_log_stats(log_file_path):
    """
    Get statistics about the log file.
    """
    if not log_file_path or not os.path.exists(log_file_path):
        return None
    
    try:
        stat = os.stat(log_file_path)
        return {
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'lines': sum(1 for _ in open(log_file_path, 'r', encoding='utf-8'))
        }
    except Exception:
        return None
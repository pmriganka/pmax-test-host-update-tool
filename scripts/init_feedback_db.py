"""
Database initialization script for feedback system.
This script creates the SQLite database and table for storing feedback.
"""

import sqlite3
import os

def init_feedback_db():
    """Initialize the feedback database."""
    db_path = 'feedback.db'
    
    try:
        # Connect to database (will be created if it doesn't exist)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create feedback table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                issue TEXT NOT NULL,
                status TEXT DEFAULT 'Ongoing',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for better performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_feedback_status 
            ON feedback(status)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_feedback_created_at 
            ON feedback(created_at)
        ''')
        
        conn.commit()
        conn.close()
        
        print(f"✅ Feedback database initialized successfully at {os.path.abspath(db_path)}")
        return True
        
    except Exception as e:
        print(f"❌ Error initializing feedback database: {str(e)}")
        return False

if __name__ == "__main__":
    init_feedback_db()

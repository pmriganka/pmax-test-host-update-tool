import streamlit as st
import requests
import re
import os
from typing import Optional, Tuple

class AuthenticationService:
    """Service for handling Bearer Token Authentication"""
    
    def __init__(self):
        self.api_base_url = os.getenv('QTEST_API_BASE_URL', 'https://qtest.gtie.dell.com/api/v3')
        self.project_id = os.getenv('QTEST_PROJECT_ID', '442')
    
    def validate_bearer_token_format(self, token_string: str) -> bool:
        """Validate that the token follows the format 'Bearer <token>'"""
        if not token_string or not isinstance(token_string, str):
            return False
        
        # Check if it starts with "Bearer " followed by non-space characters
        pattern = r'^Bearer\s+\S+$'
        return bool(re.match(pattern, token_string.strip()))
    
    def extract_token(self, bearer_string: str) -> Optional[str]:
        """Extract the actual token from 'Bearer <token>' string"""
        if not self.validate_bearer_token_format(bearer_string):
            return None
        
        # Split and return the token part
        parts = bearer_string.strip().split(' ', 1)
        if len(parts) == 2:
            return parts[1]
        return None
    
    def test_token_validity(self, token: str) -> Tuple[bool, str]:
        """Test if the token is valid by making a test API call"""
        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            # Make a simple API call to test the token
            # Using projects endpoint as it's usually accessible
            test_url = f"{self.api_base_url}/projects"
            response = requests.get(test_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return True, "Token is valid"
            elif response.status_code == 401:
                return False, "Invalid or expired token"
            elif response.status_code == 403:
                return False, "Insufficient permissions"
            else:
                return False, f"API returned status {response.status_code}"
                
        except requests.exceptions.RequestException as e:
            return False, f"Network error: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def authenticate_user(self, bearer_token_input: str) -> Tuple[bool, str, Optional[str]]:
        """
        Main authentication method
        
        Args:
            bearer_token_input: The full bearer token string from user
            
        Returns:
            Tuple of (is_authenticated, message, extracted_token)
        """
        # Validate format
        if not self.validate_bearer_token_format(bearer_token_input):
            return False, "Invalid format. Please use format: 'Bearer <token>'", None
        
        # Extract token
        token = self.extract_token(bearer_token_input)
        if not token:
            return False, "Failed to extract token", None
        
        # Test token validity
        is_valid, message = self.test_token_validity(token)
        
        if is_valid:
            # Store in session state
            st.session_state['authenticated'] = True
            st.session_state['bearer_token'] = bearer_token_input
            st.session_state['extracted_token'] = token
            return True, "Authentication successful", token
        else:
            return False, f"Authentication failed: {message}", None
    
    def logout(self):
        """Clear authentication session"""
        keys_to_clear = ['authenticated', 'bearer_token', 'extracted_token']
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
    
    def is_authenticated(self) -> bool:
        """Check if user is currently authenticated"""
        return st.session_state.get('authenticated', False)
    
    def get_auth_headers(self) -> dict:
        """Get authentication headers for API calls"""
        if self.is_authenticated():
            token = st.session_state.get('extracted_token')
            if token:
                return {
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                }
        return {}
    
    def get_bearer_token(self) -> Optional[str]:
        """Get the full bearer token string"""
        return st.session_state.get('bearer_token')

def display_login_page():
    """Display the login/authentication page"""
    st.set_page_config(
        page_title="TestHost Pro - Authentication",
        page_icon="🔐",
        layout="centered"
    )
    
    # Custom CSS for login page
    st.markdown("""
    <style>
        .login-container {
            max-width: 600px;
            margin: 0 auto;
            padding: 2rem;
            text-align: center;
        }
        .token-input {
            font-family: 'Courier New', monospace;
            font-size: 14px;
        }
        .example-token {
            background: #f0f2f6;
            padding: 0.5rem;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            margin: 1rem 0;
        }
        .error-message {
            background: #ffebee;
            color: #c62828;
            padding: 1rem;
            border-radius: 4px;
            margin: 1rem 0;
        }
        .success-message {
            background: #e8f5e8;
            color: #2e7d32;
            padding: 1rem;
            border-radius: 4px;
            margin: 1rem 0;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Login container
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    
    # App title and icon
    st.markdown("# 🔐 TestHost Pro")
    st.markdown("## Enterprise Host & Test Management")
    
    # Authentication form
    with st.form("authentication_form"):
        st.markdown("### Please enter your Bearer Token")
        
        st.markdown("""
        **Format Requirements:**
        - Must start with "Bearer " (note the space)
        - Followed by your actual token
        - Example: `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
        """)
        
        # Example token display
        st.markdown(
            '<div class="example-token">Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...</div>',
            unsafe_allow_html=True
        )
        
        # Token input
        bearer_token = st.text_area(
            "Bearer Token",
            placeholder="Bearer your_token_here",
            help="Enter the complete bearer token including 'Bearer ' prefix",
            key="bearer_token_input",
            height=100
        )
        
        # Submit button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            submit_button = st.form_submit_button(
                "🔓 Authenticate",
                use_container_width=True,
                type="primary"
            )
    
    # Handle authentication
    if submit_button:
        if not bearer_token.strip():
            st.error("⚠️ Please enter a bearer token")
        else:
            auth_service = AuthenticationService()
            is_auth, message, token = auth_service.authenticate_user(bearer_token)
            
            if is_auth:
                st.markdown(
                    f'<div class="success-message">✅ {message}</div>',
                    unsafe_allow_html=True
                )
                st.success("🎉 Redirecting to application...")
                st.rerun()
            else:
                st.markdown(
                    f'<div class="error-message">❌ {message}</div>',
                    unsafe_allow_html=True
                )
    
    # Help section
    with st.expander("📖 Need Help?"):
        st.markdown("""
        ### How to get your Bearer Token:
        
        1. **Log in to qTest**
        2. **Navigate to API settings**
        3. **Generate a new API token**
        4. **Copy the token**
        5. **Enter it here with 'Bearer ' prefix**
        
        ### Common Issues:
        
        - **Missing 'Bearer ' prefix**: Make sure to include "Bearer " at the beginning
        - **Extra spaces**: Remove any extra spaces before or after the token
        - **Expired token**: Generate a new token if yours has expired
        - **Incorrect permissions**: Ensure your token has API access permissions
        
        ### Security:
        
        - Your token is stored only in your current session
        - Never share your token with others
        - Logout when done to clear the token
        """)
    
    st.markdown('</div>', unsafe_allow_html=True)

def require_authentication():
    """Decorator/function to require authentication before accessing pages"""
    if 'authenticated' not in st.session_state or not st.session_state['authenticated']:
        display_login_page()
        return False
    return True

def get_auth_service():
    """Get an instance of the authentication service"""
    return AuthenticationService()

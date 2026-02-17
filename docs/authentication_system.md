# Bearer Token Authentication System

## Overview

TestHost Pro now implements a secure Bearer Token authentication system that requires users to authenticate before accessing any application features. The system validates tokens against the qTest API and ensures only authorized users can access the application.

## 🔐 Authentication Flow

### 1. Login Page
When users first access the application, they're presented with a login screen that requires:
- **Bearer Token**: Full token string in format `Bearer <token>`
- **Format Validation**: Ensures proper "Bearer " prefix
- **Token Verification**: Validates against qTest API
- **Session Management**: Stores authentication state securely

### 2. Token Format Requirements
```
Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Requirements:**
- Must start with "Bearer " (note the space)
- Followed by valid API token
- No extra spaces before or after
- Token must be valid for qTest API

### 3. Authentication Process
1. **Format Validation**: Regex pattern matching for `Bearer <token>`
2. **Token Extraction**: Remove "Bearer " prefix
3. **API Validation**: Test token against qTest API
4. **Session Storage**: Store in Streamlit session state
5. **Access Grant**: Allow access to application features

## 🛡️ Security Features

### Token Validation
- **Format Checking**: Regex validation ensures proper format
- **API Testing**: Validates token against live qTest API
- **Error Handling**: Clear error messages for invalid tokens
- **Session Security**: Tokens stored only in session memory

### Session Management
- **Temporary Storage**: Tokens not persisted to disk
- **Automatic Logout**: Session cleared on browser close
- **Manual Logout**: Users can explicitly logout
- **Token Masking**: Display masked token in sidebar

### Error Handling
- **Invalid Format**: Clear format requirements
- **Expired Tokens**: Detect and report expired tokens
- **Network Errors**: Handle API connectivity issues
- **Permission Issues**: Detect insufficient permissions

## 📱 User Interface

### Login Screen
- **Professional Design**: Clean, centered layout
- **Clear Instructions**: Format examples and requirements
- **Help Section**: Detailed troubleshooting guide
- **Visual Feedback**: Success/error messages

### Authenticated Session
- **Sidebar Status**: Shows authentication status
- **Token Display**: Masked token for verification
- **Logout Button**: Easy session termination
- **Session Info**: Current authentication state

## 🔧 Technical Implementation

### Authentication Service (`services/auth_service.py`)
```python
class AuthenticationService:
    def validate_bearer_token_format(self, token_string: str) -> bool
    def extract_token(self, bearer_string: str) -> Optional[str]
    def test_token_validity(self, token: str) -> Tuple[bool, str]
    def authenticate_user(self, bearer_token_input: str) -> Tuple[bool, str, Optional[str]]
    def logout(self) -> None
    def is_authenticated(self) -> bool
    def get_auth_headers(self) -> dict
```

### Integration Points

#### Main Application (`streamlitapp.py`)
```python
# Authentication check at entry point
if not require_authentication():
    st.stop()

# Sidebar session management
auth_service = get_auth_service()
if st.sidebar.button("🚪 Logout"):
    auth_service.logout()
    st.rerun()
```

#### Service Classes
- **Testcase**: Updated to accept auth headers
- **Updatetestcase**: Updated to accept auth headers
- **Fallback**: Maintains backward compatibility with env vars

#### API Headers
```python
# Authentication headers for API calls
headers = {
    'Authorization': 'Bearer <token>',
    'Content-Type': 'application/json'
}
```

## 🚀 Usage Guide

### For Users

#### Getting Your Token
1. **Log in to qTest**: Access your qTest instance
2. **Navigate to API Settings**: Find API/token management
3. **Generate Token**: Create new API token
4. **Copy Token**: Copy the complete token string
5. **Add Prefix**: Prepend with "Bearer " if not already included

#### Login Process
1. **Access Application**: Navigate to TestHost Pro URL
2. **Enter Token**: Input complete `Bearer <token>` string
3. **Authenticate**: Click authenticate button
4. **Success**: Redirected to main application
5. **Use Features**: Access all application functionality

#### Troubleshooting
- **Format Issues**: Ensure "Bearer " prefix and no extra spaces
- **Expired Tokens**: Generate new token in qTest
- **Permission Issues**: Ensure token has API access
- **Network Issues**: Check connectivity to qTest API

### For Developers

#### Adding Authentication to New Pages
```python
from services.auth_service import require_authentication, get_auth_service

# At the top of any new page
if not require_authentication():
    st.stop()

# Get auth headers for API calls
auth_service = get_auth_service()
auth_headers = auth_service.get_auth_headers()
```

#### Using Authenticated Services
```python
# Pass auth headers to service classes
testcase = Testcase(auth_headers)
updatetestcase = Updatetestcase(auth_headers)
```

#### API Call Pattern
```python
# All API calls should use auth headers
response = requests.get(url, headers=auth_headers)
```

## 🔒 Security Considerations

### Token Protection
- **No Persistence**: Tokens never written to disk
- **Session Only**: Stored in memory only
- **Auto-Cleanup**: Cleared on session end
- **Masked Display**: Partial token shown in UI

### API Security
- **HTTPS Required**: All API calls over HTTPS
- **Token Validation**: Real-time validation against qTest
- **Error Handling**: No sensitive info in error messages
- **Rate Limiting**: Respect API rate limits

### Best Practices
- **Token Rotation**: Regularly rotate tokens
- **Minimum Permissions**: Use least-privilege tokens
- **Secure Storage**: Never store tokens in code
- **Audit Trail**: Log authentication events

## 📋 Configuration

### Environment Variables
```bash
# Optional fallback (for backward compatibility)
API_TOKEN=your_legacy_token

# qTest API configuration
QTEST_API_BASE_URL=https://qtest.gtie.dell.com/api/v3
QTEST_PROJECT_ID=442
```

### Session State Keys
```python
st.session_state['authenticated']     # Boolean auth status
st.session_state['bearer_token']      # Full bearer token string
st.session_state['extracted_token']  # Token without Bearer prefix
```

## 🔄 Migration Guide

### From Environment Variables
1. **Existing Tokens**: Continue to work during transition
2. **New Users**: Must use bearer token format
3. **Service Classes**: Updated to accept auth headers
4. **Backward Compatibility**: Maintained for existing setups

### Update Steps
1. **Deploy New Code**: Upload authentication system
2. **Update Services**: Modify service constructors
3. **Test Authentication**: Verify login flow
4. **Remove Old Tokens**: Eventually remove env var tokens

## 🎯 Benefits

### Enhanced Security
- **Token Validation**: Real-time API validation
- **Session Management**: Secure session handling
- **Access Control**: Centralized authentication
- **Audit Trail**: Authentication logging

### Better User Experience
- **Professional Login**: Clean authentication interface
- **Clear Feedback**: Success/error messages
- **Help System**: Built-in troubleshooting
- **Session Status**: Visible authentication state

### Developer Benefits
- **Centralized Auth**: Single authentication system
- **Easy Integration**: Simple auth header usage
- **Consistent Pattern**: Standardized auth approach
- **Backward Compatible**: Gradual migration support

## 🚨 Troubleshooting

### Common Issues

#### "Invalid Format" Error
- **Cause**: Missing "Bearer " prefix or extra spaces
- **Solution**: Use format `Bearer <token>` exactly

#### "Authentication Failed" Error
- **Cause**: Invalid or expired token
- **Solution**: Generate new token in qTest

#### "Network Error" 
- **Cause**: Cannot reach qTest API
- **Solution**: Check network connectivity

#### "Insufficient Permissions"
- **Cause**: Token lacks API access
- **Solution**: Ensure token has proper permissions

### Debug Mode
Enable debug logging to troubleshoot authentication issues:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📞 Support

For authentication issues:
1. **Check Token Format**: Verify `Bearer <token>` format
2. **Test API Access**: Validate token manually
3. **Check Network**: Ensure qTest API accessibility
4. **Review Logs**: Check application logs for errors
5. **Contact Admin**: Reach out to system administrator

---

**Note**: This authentication system enhances security while maintaining backward compatibility. Users can migrate gradually from environment variable tokens to bearer token authentication.

import os
import re
from pathlib import Path

# Standard library modules
STDLIB_MODULES = {
    'os', 'sys', 'json', 'time', 'datetime', 'logging', 're', 'ast', 'pathlib',
    'threading', 'subprocess', 'base64', 'io', 'html', 'sqlite3', 'concurrent',
    'socket', 'ssl', 'urllib', 'http', 'collections', 'itertools', 'functools'
}

# Collect all third-party imports
third_party_imports = set()
project_root = Path('.')

# Skip these directories
skip_dirs = {'myvenv', '__pycache__', '.git', 'node_modules', 'scripts'}

for py_file in project_root.rglob('*.py'):
    # Skip files in excluded directories and scan_imports.py itself
    if any(skip_dir in str(py_file) for skip_dir in skip_dirs) or py_file.name == 'scan_imports.py':
        continue
    
    try:
        with open(py_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Find all import statements
        import_pattern = r'^(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)'
        for match in re.finditer(import_pattern, content, re.MULTILINE):
            module = match.group(1).split('.')[0]
            # Skip local imports (services, views, components) and stdlib
            if module not in STDLIB_MODULES and module not in ['services', 'views', 'components']:
                third_party_imports.add(module)
                
    except Exception as e:
        print(f"Error processing {py_file}: {e}")

# Map common import names to package names
PACKAGE_MAPPING = {
    'streamlit': 'streamlit',
    'streamlit_quill': 'streamlit-quill',
    'streamlit_autorefresh': 'streamlit-autorefresh',
    'numpy': 'numpy',
    'pandas': 'pandas',
    'requests': 'requests',
    'dotenv': 'python-dotenv',
    'paramiko': 'paramiko',
    'pyVmomi': 'pyvmomi',
    'pyVim': 'pyvmomi',
    'vmware': 'vmware-vcenter',
    'com': 'vmware-vapi-common-client',
    'ansible_runner': 'ansible-runner',
    'ansible': 'ansible'
}

print("Third-party packages used in the project:")
print("-" * 40)
packages_used = set()
for imp in sorted(third_party_imports):
    package = PACKAGE_MAPPING.get(imp, imp)
    packages_used.add(package)
    print(f"{imp} -> {package}")

print("\n\nPackages that should be in requirements.txt:")
print("-" * 40)
for pkg in sorted(packages_used):
    print(pkg)

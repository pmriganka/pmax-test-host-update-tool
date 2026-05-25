import ast
import os
from pathlib import Path

# Collect all imports
imports = set()
project_root = Path('.')

# Skip these directories
skip_dirs = {'myvenv', '__pycache__', '.git', 'node_modules'}

for py_file in project_root.rglob('*.py'):
    # Skip files in excluded directories
    if any(skip_dir in str(py_file) for skip_dir in skip_dirs):
        continue
    
    try:
        with open(py_file, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
            
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split('.')[0]
                    imports.add(module)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split('.')[0]
                    imports.add(module)
    except Exception as e:
        print(f"Error processing {py_file}: {e}")

# Print sorted imports
print("All imported modules:")
print("-" * 40)
for imp in sorted(imports):
    print(imp)

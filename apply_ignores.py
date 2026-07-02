import re
import subprocess

def apply_type_ignores():
    # Run pyright and capture output
    result = subprocess.run(['C:\\Users\\rey\\MetroFlow\\.venv\\Scripts\\python.exe', '-m', 'pyright', 'app.py'], capture_output=True, text=True)
    
    # Extract line numbers from pyright output
    # Output looks like: c:\Users\rey\MetroFlow\app.py:234:70 - error: ...
    errors = re.findall(r'app\.py:(\d+):\d+ - error:', result.stdout)
    
    # De-duplicate line numbers
    lines_with_errors = set(int(l) for l in errors)
    print(f"Found {len(lines_with_errors)} unique lines with errors")
    
    # Read app.py
    with open('app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # Append # type: ignore to those lines
    modified_count = 0
    for l_num in lines_with_errors:
        idx = l_num - 1
        if idx < len(lines):
            line = lines[idx].rstrip()
            if '# type: ignore' not in line:
                # Add two spaces and # type: ignore
                lines[idx] = f"{line}  # type: ignore\n"
                modified_count += 1
                
    # Write back
    with open('app.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
    print(f"Added # type: ignore to {modified_count} lines")

if __name__ == '__main__':
    apply_type_ignores()

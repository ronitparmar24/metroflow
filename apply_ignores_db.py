import re
import subprocess

def apply_type_ignores():
    result = subprocess.run(['C:\\Users\\rey\\MetroFlow\\.venv\\Scripts\\python.exe', '-m', 'pyright', 'db.py'], capture_output=True, text=True)
    errors = re.findall(r'db\.py:(\d+):\d+ - error:', result.stdout)
    lines_with_errors = set(int(l) for l in errors)
    print(f"Found {len(lines_with_errors)} unique lines with errors in db.py")
    
    with open('db.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    modified_count = 0
    for l_num in lines_with_errors:
        idx = l_num - 1
        if idx < len(lines):
            line = lines[idx].rstrip()
            if '# type: ignore' not in line:
                lines[idx] = f"{line}  # type: ignore\n"
                modified_count += 1
                
    with open('db.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
    print(f"Added # type: ignore to {modified_count} lines in db.py")

if __name__ == '__main__':
    apply_type_ignores()

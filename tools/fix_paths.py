import os
import glob
from pathlib import Path

files = glob.glob('source-manager/*.py')
for file in files:
    if 'common.py' in file:
        continue
    content = Path(file).read_text(encoding='utf-8')
    content = content.replace('PONYO_HOME / "data"', 'DATA_DIR')
    content = content.replace("PONYO_HOME / 'data'", 'DATA_DIR')
    content = content.replace('PONYO_HOME / "reports"', 'REPORT_DIR')
    content = content.replace("PONYO_HOME / 'reports'", 'REPORT_DIR')
    content = content.replace('PONYO_HOME / "config"', 'CONFIG_DIR')
    content = content.replace("PONYO_HOME / 'config'", 'CONFIG_DIR')
    content = content.replace('PONYO_HOME / "logs"', 'LOG_DIR')
    content = content.replace("PONYO_HOME / 'logs'", 'LOG_DIR')
    
    # Scripts are in CODE_DIR, so PONYO_HOME / "script.py" -> CODE_DIR / "script.py"
    import re
    # We replace PONYO_HOME / "xxx.py" with CODE_DIR / "xxx.py"
    content = re.sub(r'PONYO_HOME \/ "(.*?\.py)"', r'CODE_DIR / "\1"', content)
    content = re.sub(r"PONYO_HOME \/ '(.*?\.py)'", r"CODE_DIR / '\1'", content)
    
    # Add imports to common
    if 'DATA_DIR' in content or 'REPORT_DIR' in content or 'CONFIG_DIR' in content or 'LOG_DIR' in content or 'CODE_DIR' in content:
        if 'from common import ' in content:
            new_imports = []
            if 'DATA_DIR' in content: new_imports.append('DATA_DIR')
            if 'REPORT_DIR' in content: new_imports.append('REPORT_DIR')
            if 'CONFIG_DIR' in content: new_imports.append('CONFIG_DIR')
            if 'LOG_DIR' in content: new_imports.append('LOG_DIR')
            if 'CODE_DIR' in content: new_imports.append('CODE_DIR')
            
            for imp in new_imports:
                if imp not in content:
                    content = content.replace('from common import PONYO_HOME', f'from common import PONYO_HOME, {imp}')
                    content = content.replace('from common import PONYO_HOME as HERE', f'from common import PONYO_HOME as HERE, {imp}')
                    content = content.replace('from common import PONYO_ROOT', f'from common import PONYO_ROOT, {imp}')

    Path(file).write_text(content, encoding='utf-8')

import glob
from pathlib import Path

files = glob.glob('source-manager/*.py')
for file in files:
    if 'common.py' in file:
        continue
    content = Path(file).read_text(encoding='utf-8')
    if 'from common import ' in content:
        # replace any remaining PONYO_HOME as HERE with DATA_DIR, etc. if needed.
        # But actually, let's just make sure DATA_DIR, REPORT_DIR, CODE_DIR, CONFIG_DIR, LOG_DIR, PONYO_ROOT are imported if used.
        used_vars = [v for v in ['DATA_DIR', 'REPORT_DIR', 'CODE_DIR', 'CONFIG_DIR', 'LOG_DIR', 'PONYO_ROOT'] if v in content]
        if used_vars:
            for v in used_vars:
                if v not in content.split('from common import ')[1].split('\n')[0]:
                    content = content.replace('from common import PONYO_HOME', f'from common import PONYO_HOME, {v}')
                    content = content.replace('from common import assert_no_proxy, classify, compute_fingerprint\nfrom common import PONYO_HOME', f'from common import assert_no_proxy, classify, compute_fingerprint\nfrom common import PONYO_HOME, {v}')
                    if 'as HERE' in content:
                        content = content.replace('from common import PONYO_HOME as HERE', f'from common import PONYO_HOME as HERE, {v}')
            Path(file).write_text(content, encoding='utf-8')

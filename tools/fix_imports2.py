import os
from pathlib import Path

def process(path_dir):
    for root, _, files in os.walk(path_dir):
        for name in files:
            if not name.endswith('.py'):
                continue
            path = Path(root) / name
            content = path.read_text(encoding='utf-8')
            new_content = content
            
            # Replacements
            new_content = new_content.replace('from core', 'from ponyo_source_manager.core')
            new_content = new_content.replace('import core\n', 'from ponyo_source_manager import core\n')
            new_content = new_content.replace('from discovery', 'from ponyo_source_manager.discovery')
            new_content = new_content.replace('from probes', 'from ponyo_source_manager.probes')
            new_content = new_content.replace('from scoring', 'from ponyo_source_manager.scoring')
            new_content = new_content.replace('from publish', 'from ponyo_source_manager.publishing')
            
            new_content = new_content.replace('ponyo_source_manager.publishing.children_api', 'ponyo_source_manager.api.children')
            new_content = new_content.replace('ponyo_source_manager.publishing.live_manager', 'ponyo_source_manager.probes.live')
            new_content = new_content.replace('ponyo_source_manager.probes.test_playback', 'ponyo_source_manager.probes.playback')
            new_content = new_content.replace('ponyo_source_manager.publishing.publish', 'ponyo_source_manager.publishing.release')
            
            if new_content != content:
                print(f"Updating {path}")
                path.write_text(new_content, encoding='utf-8')

process('source-manager/src/ponyo_source_manager')
process('source-manager/tests')
process('source-manager/tools')

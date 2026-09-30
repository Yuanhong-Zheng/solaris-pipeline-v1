"""Publish verified artifacts and source-controlled web assets to viz-hub."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from prepare_inputs import PROJECT, SOLARIS, ROOT, SPECS, atomic_json

SITE = ROOT / 'viz-hub/drops/solaris-gpt-blender'


def copy(src, dest):
    if not src.is_file():
        raise FileNotFoundError(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + '.tmp')
    shutil.copyfile(src, part)
    part.replace(dest)


def publish(site, output_root, spec_file=None):
    specs = json.loads(spec_file.read_text()) if spec_file else SPECS
    entries = []
    for name, spec in specs.items():
        output = output_root / name
        validation = json.loads((output / 'validation.json').read_text())
        if len(validation['videos']) != 5 or not all(v['decode_ok'] for v in validation['videos'].values()):
            raise ValueError(f'{name}: incomplete validation')
        metadata = json.loads((output / 'metadata.json').read_text())
        condition = json.loads((PROJECT / 'inputs' / name / 'condition.json').read_text())
        provenance = json.loads((PROJECT / 'inputs' / name / 'provenance.json').read_text())
        context = {}
        for key, suffix in [('keyframes', 'alpha_keyframes.jpg'), ('actions', 'actions.png')]:
            relative = f'inputs/{name}_{suffix}'
            copy(SOLARIS / 'output/solaris/input_frames' / f'{name}_{suffix}', site / relative)
            context[key] = relative
        entry = {'name': name, 'label': spec['label'], 'category': spec['category'],
                 'instruction': spec['instruction'], 'environment': spec['environment'],
                 'render': metadata['render'], 'actions': {}, 'players': {}, 'downloads': {},
                 'context': context, 'modeling': metadata['modeling'],
                 'validation': validation, 'windows': provenance['players']}
        for player, video in [('alpha', 'blender_world.mp4'), ('bravo', 'blender_bravo.mp4')]:
            assets = {
                'gt': (output / f'gt_{player}.mp4', f'videos/{name}_gt_{player}.mp4'),
                'blender': (output / video, f'videos/{name}_blender_{player}.mp4'),
                'input': (PROJECT / 'inputs' / name / f'{player}_first.png', f'inputs/{name}_{player}_first.png'),
                'poster': (output / f'{player}_preview_0001.png', f'thumbs/{name}_{player}_0001.png'),
            }
            entry['players'][player] = {}
            for key, (source, relative) in assets.items():
                copy(source, site / relative)
                entry['players'][player][key] = relative
            previews = []
            for frame in (1, 86, 172, 257):
                relative = f'thumbs/{name}_{player}_{frame:04d}.png'
                if frame != 1:
                    copy(output / f'{player}_preview_{frame:04d}.png', site / relative)
                previews.append({'frame': frame, 'path': relative})
            entry['players'][player]['previews'] = previews
            entry['actions'][player] = condition['players'][player]['actions']
        files = {
            'comparison': (output / 'comparison.mp4', f'videos/{name}_comparison.mp4'),
            'solaris': (SOLARIS / 'output/solaris' / name / 'video_0_side_by_side.mp4', f'videos/{name}_solaris.mp4'),
            'blend': (output / f'{name}.blend', f'projects/{name}.blend'),
            'metadata': (output / 'metadata.json', f'projects/{name}_metadata.json'),
            'condition': (PROJECT / 'inputs' / name / 'condition.json', f'inputs/{name}_condition.json'),
            'provenance': (PROJECT / 'inputs' / name / 'provenance.json', f'inputs/{name}_provenance.json'),
            'validation': (output / 'validation.json', f'projects/{name}_validation.json'),
        }
        for key, (source, relative) in files.items():
            copy(source, site / relative)
            entry['downloads'][key] = relative
        entries.append(entry)
    is_astra = output_root.name == 'outputs_astra' or 'astra' in site.name.lower()
    title = ('Solaris / GPT-6 Astra → Blender 世界对比' if is_astra else 'Solaris / Blender 世界对比')
    method = ('GPT-6 Astra 读取双人首帧和动作图，生成场景布局参数；动作序列驱动共享三维世界，再由 Blender CPU Workbench 渲染。'
              if is_astra else 'AI 根据两张输入首帧写入场景参数，动作序列驱动共享三维世界，分别渲染 Alpha / Bravo。')
    data = {'meta': {'title': title, 'fps': 20, 'frames': 257, 'duration': 12.85,
        'render_size': [1280, 704], 'gt_view_size': [640, 352], 'comparison_size': [1280, 704],
        'engine': 'Blender Workbench · CPU / llvmpipe', 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'method': method, 'stage': '阶段 1 · Blender 建模；未接入视频生成模型'}, 'datasets': entries}
    site.mkdir(parents=True, exist_ok=True)
    for asset in (PROJECT / 'web').iterdir():
        if asset.is_file():
            copy(asset, site / asset.name)
    atomic_json(site / 'data.json', data)
    print('PUBLISHED', site, flush=True)
    print(f'URL http://10.80.198.139:21007/d/{site.name}/', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', type=Path, default=SITE)
    parser.add_argument('--output-root', type=Path, default=PROJECT / 'outputs')
    parser.add_argument('--spec-file', type=Path)
    args = parser.parse_args()
    publish(args.site, args.output_root, args.spec_file)

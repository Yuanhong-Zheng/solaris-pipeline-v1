"""Ask GPT-6 Astra for compact Blender scene layouts from the real conditions.

The model sees the two condition images and the action visualization. It does
not receive future pose coordinates or generated videos. Responses are parsed
into the stable scene_specs schema used by the Blender builder; raw model text
is retained for audit without credentials.
"""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

PROJECT = Path(__file__).resolve().parent
SOLARIS = PROJECT.parent
# Keep the authored input/task schema separate from the generated builder
# snapshot committed as scene_specs.json.
BASE_SPECS = json.loads((PROJECT / 'scene_specs_base.json').read_text())
MODEL = 'gpt-6-astra'
API_URL = 'https://api.zcloudapi.com/v1/responses'
ALLOWED_ENVIRONMENTS = {'flat', 'savanna', 'village'}
ALLOWED_LANDMARKS = {'none', 'sheep', 'distant_animals', 'village_right', 'village_behind', 'river_acacia'}


def data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = 'image/png' if suffix == '.png' else 'image/jpeg'
    return 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


def extract_text(obj: dict) -> str:
    if isinstance(obj.get('output_text'), str):
        return obj['output_text']
    parts = []
    for item in obj.get('output', []) or []:
        for content in item.get('content', []) or []:
            if isinstance(content, dict) and isinstance(content.get('text'), str):
                parts.append(content['text'])
    return ''.join(parts)


def parse_json(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict): return value
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', cleaned, flags=re.S)
    if match:
        value = json.loads(match.group(0))
        if isinstance(value, dict): return value
    raise ValueError('Astra did not return a JSON object')


def finite_number(value, name):
    result = float(value)
    if not math.isfinite(result): raise ValueError(name + ' must be finite')
    return result


def normalize(name: str, candidate: dict) -> dict:
    base = BASE_SPECS[name]
    environment = candidate.get('environment', base['environment'])
    if environment not in ALLOWED_ENVIRONMENTS: environment = base['environment']
    landmarks = candidate.get('landmarks', base['landmarks'])
    if landmarks not in ALLOWED_LANDMARKS: landmarks = base['landmarks']
    initial = candidate.get('initial') if isinstance(candidate.get('initial'), dict) else {}
    alpha = initial.get('alpha') if isinstance(initial.get('alpha'), dict) else {}
    bravo = initial.get('bravo') if isinstance(initial.get('bravo'), dict) else {}
    def player(fallback, source):
        position = source.get('position', fallback['position'])
        if not isinstance(position, (list, tuple)) or len(position) != 3: position = fallback['position']
        try: position = [finite_number(v, 'position') for v in position]
        except Exception: position = list(fallback['position'])
        try: yaw = finite_number(source.get('yaw', fallback['yaw']), 'yaw')
        except Exception: yaw = float(fallback['yaw'])
        try: pitch = finite_number(source.get('pitch', 0.0), 'pitch')
        except Exception: pitch = 0.0
        return {'position': position, 'yaw': yaw, 'pitch': max(-1.4, min(1.4, pitch))}
    # Re-anchor Alpha at origin so geometry remains stable across model outputs.
    a = player(base['initial']['alpha'], alpha)
    b = player(base['initial']['bravo'], bravo)
    ax, ay, az = a['position']
    b['position'] = [b['position'][i] - a['position'][i] for i in range(3)]
    a['position'] = [0.0, 0.0, 0.0]
    notes = candidate.get('notes', [])
    if isinstance(notes, str): notes = [notes]
    if not isinstance(notes, list): notes = []
    return {**base, 'environment': environment, 'landmarks': landmarks,
            'initial': {'alpha': a, 'bravo': b},
            'astra_notes': [str(x)[:500] for x in notes[:8]],
            'astra_model': MODEL}


def call_one(name: str, api_key: str) -> dict:
    base = BASE_SPECS[name]
    input_root = SOLARIS / 'output' / 'solaris' / 'input_frames'
    cond_root = PROJECT / 'inputs' / name
    content = [
        {'type': 'input_text', 'text': f'''You are GPT-6 Astra acting as a Blender scene designer. Design a compact, deterministic proxy world for the Solaris multiplayer task {name}.
Task label: {base['label']}. Category: {base['category']}.
Task instruction: {base['instruction']}
The Alpha and Bravo images below are the only initial condition images. The action image summarizes the 257-frame keyboard/mouse sequence. Infer a plausible shared Minecraft-style world layout that can be rendered with simple boxes and low-poly objects.
Do not claim exact hidden coordinates and do not use future ground-truth poses. Alpha must start at [0,0,0]. Bravo position is relative to Alpha in approximate block units. Yaw and pitch are radians. Choose environment from flat, savanna, village. Choose landmarks from none, sheep, distant_animals, village_right, village_behind, river_acacia.
Return ONLY one JSON object with this schema: {{"environment":"flat|savanna|village","landmarks":"none|sheep|distant_animals|village_right|village_behind|river_acacia","initial":{{"alpha":{{"position":[0,0,0],"yaw":0,"pitch":0}},"bravo":{{"position":[x,y,0],"yaw":0,"pitch":0}}}},"notes":["short visual rationale"]}}'''.strip()},
        {'type': 'input_image', 'image_url': data_url(cond_root / 'alpha_first.png')},
        {'type': 'input_image', 'image_url': data_url(cond_root / 'bravo_first.png')},
        {'type': 'input_image', 'image_url': data_url(input_root / f'{name}_actions.png')},
    ]
    payload = {'model': MODEL, 'input': [{'role': 'user', 'content': content}],
               'max_output_tokens': 500, 'store': False}
    request = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), headers={
        'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json',
        'User-Agent': 'solaris-gpt-blender-astra/1.0'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read(); status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read(); status = error.code
    if status != 200:
        raise RuntimeError(f'HTTP {status}: {raw[:600].decode("utf-8", "replace")}')
    response = json.loads(raw)
    text = extract_text(response)
    normalized = normalize(name, parse_json(text))
    return {'dataset': name, 'model': response.get('model', MODEL),
            'response_id': response.get('id'), 'raw_text': text,
            'spec': normalized, 'generated_utc': datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', nargs='+', choices=sorted(BASE_SPECS))
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--output', type=Path, default=PROJECT / 'astra_scene_specs.json')
    args = parser.parse_args()
    key = os.environ.get('ZCLOUD_API_KEY')
    if not key: raise SystemExit('ZCLOUD_API_KEY is required')
    names = args.dataset or list(BASE_SPECS)
    results = {}
    failures = {}
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, len(names)))) as pool:
        futures = {pool.submit(call_one, name, key): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result(); results[name] = result
                print('ASTRA_SPEC_OK', name, result['model'], flush=True)
            except Exception as error:
                failures[name] = str(error); print('ASTRA_SPEC_FAILED', name, error, flush=True)
    if failures: raise SystemExit(json.dumps({'failures': failures}, ensure_ascii=False))
    ordered = {name: results[name] for name in names}
    args.output.write_text(json.dumps({'model': MODEL, 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'datasets': ordered}, ensure_ascii=False, indent=2) + '\n')
    # This is the exact builder-facing file; raw responses remain alongside it.
    builder_specs = {name: results[name]['spec'] for name in names}
    (PROJECT / 'scene_specs_astra_builder.json').write_text(json.dumps(builder_specs, ensure_ascii=False, indent=2) + '\n')
    print('ASTRA_SPECS_WRITTEN', args.output, flush=True)
    print('ASTRA_BUILDER_SPECS_WRITTEN', PROJECT / 'scene_specs_astra_builder.json', flush=True)

if __name__ == '__main__': main()

"""Extract exactly the first inference sample, keeping only images and actions.

The renderer consumes inputs/<dataset>/condition.json, which deliberately has
no recorded positions, yaw, pitch, future images, or GT video paths.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
SOLARIS = PROJECT.parent
ROOT = SOLARIS.parent
SPECS = json.loads((PROJECT / 'scene_specs.json').read_text())
FPS, FRAMES = 20, 257
FFMPEG = Path(os.environ.get('FFMPEG', str(ROOT / 'miniconda3/envs/javisdit/bin/ffmpeg')))
FFPROBE = FFMPEG.with_name('ffprobe')


def atomic_json(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def prepare(name):
    spec = SPECS[name]
    ids = SOLARIS / 'src/data/eval_ids' / f'eval_ids_{name}.json'
    episode, a_start, a_stop, b_start, b_stop = json.loads(ids.read_text())[0]
    assert episode == 0 and a_stop - a_start == b_stop - b_start == FRAMES
    output = PROJECT / 'inputs' / name
    output.mkdir(parents=True, exist_ok=True)
    conditions = {'dataset': name, 'fps': FPS, 'frames': FRAMES,
                  'instruction': spec['instruction'], 'players': {}}
    provenance = {'eval_ids': str(ids), 'sample_index': 0, 'episode': episode,
                  'players': {}, 'first_image_source': 'first GT frame of saved inference composite',
                  'note': 'Only action dictionaries and the two frame-0 images enter modeling.'}
    composite = SOLARIS / 'output/solaris' / name / 'video_0_side_by_side.mp4'
    stream = json.loads(subprocess.check_output([str(FFPROBE), '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,r_frame_rate,nb_frames', '-of', 'json', str(composite)]))['streams'][0]
    assert (stream['width'], stream['height'], stream['r_frame_rate'], int(stream['nb_frames'])) == (1280, 704, '20/1', FRAMES), stream
    for player, start, stop, crop_y in [('alpha', a_start, a_stop, 0), ('bravo', b_start, b_stop, 352)]:
        source = SOLARIS / 'datasets/eval' / spec['folder'] / 'test' / f'000000_{player.title()}_instance_000.json'
        raw = json.loads(source.read_text())
        actions = [row['action'] for row in raw[start:stop]]
        if len(actions) != FRAMES:
            raise ValueError(f'{name}/{player}: insufficient actions')
        conditions['players'][player] = {'first_image': f'{player}_first.png', 'actions': actions}
        provenance['players'][player] = {'actions_source': str(source), 'start': start, 'stop_exclusive': stop,
            'sha256': hashlib.sha256(json.dumps(actions, sort_keys=True).encode()).hexdigest()}
        subprocess.run([str(FFMPEG), '-v', 'error', '-y', '-threads', '2', '-i', str(composite),
            '-vf', f'crop=640:352:0:{crop_y}', '-frames:v', '1', '-threads', '2', str(output / f'{player}_first.png')], check=True)
    atomic_json(output / 'condition.json', conditions)
    atomic_json(output / 'provenance.json', provenance)
    print('INPUT_READY', name, f'Alpha [{a_start},{a_stop}); Bravo [{b_start},{b_stop})', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', nargs='+', choices=list(SPECS))
    args = parser.parse_args()
    for name in args.dataset or SPECS:
        prepare(name)

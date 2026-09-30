"""Build, render, encode and verify each episode, then publish the static site."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from prepare_inputs import PROJECT, SOLARIS, SPECS, FFMPEG, FFPROBE, atomic_json, prepare


def validate_video(path, width, height):
    probe = json.loads(subprocess.check_output([str(FFPROBE), '-v', 'error', '-count_frames',
        '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,width,height,r_frame_rate,nb_read_frames,pix_fmt:format=duration',
        '-of', 'json', str(path)]))
    stream = probe['streams'][0]
    actual = (stream['codec_name'], stream['width'], stream['height'], stream['r_frame_rate'], int(stream['nb_read_frames']))
    if actual != ('h264', width, height, '20/1', 257):
        raise ValueError(f'{path}: {actual}')
    subprocess.run([str(FFMPEG), '-v', 'error', '-xerror', '-threads', '2', '-i', str(path),
                    '-f', 'null', '-'], check=True, stdout=subprocess.DEVNULL)
    return {**stream, 'duration': float(probe['format']['duration']), 'decode_ok': True, 'bytes': path.stat().st_size}


def fingerprint(name, spec_file):
    digest = hashlib.sha256()
    for p in [PROJECT/'render_solaris_scene.py', PROJECT/'motion.py', spec_file,
              PROJECT/'run_pipeline.py', PROJECT/'inputs'/name/'condition.json']:
        digest.update(p.read_bytes())
    return digest.hexdigest()


def render_one(name, force, keep_frames, output_root, spec_file):
    output = output_root / name
    output.mkdir(parents=True, exist_ok=True)
    code_hash = fingerprint(name, spec_file)
    record = output / 'validation.json'
    if not force and record.exists():
        saved = json.loads(record.read_text())
        if saved.get('fingerprint') == code_hash and all((output/f).exists() for f in saved['videos']):
            print('SKIP_VERIFIED', name, flush=True)
            return
    started = time.monotonic()
    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'LIBGL_ALWAYS_SOFTWARE': '1',
           'MESA_LOADER_DRIVER_OVERRIDE': 'llvmpipe', 'GALLIUM_DRIVER': 'llvmpipe',
           'LP_NUM_THREADS': '8', 'OMP_NUM_THREADS': '8', 'BLENDER_THREADS': '8'}
    with tempfile.TemporaryDirectory(prefix=f'solaris_blender_{name}_', dir='/tmp') as tmp:
        temporary = Path(tmp)
        frames = output / 'frames' if keep_frames else temporary / 'frames'
        command = [str(SOLARIS/'blender-foundation/blender-run'), str(PROJECT/'render_solaris_scene.py'),
                   '--no-xvfb', '--python-exit-code', '1', '--', '--dataset', name,
                   '--frames-dir', str(frames), '--output-root', str(output_root), '--spec-file', str(spec_file)]
        print('RENDER_START', name, flush=True)
        with (output/'render.log').open('w') as log:
            subprocess.run(command, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
        videos = {}
        def encode(filename, inputs, filters=None, dimensions=(1280,704), lossless=False):
            target = temporary / filename
            cmd = [str(FFMPEG), '-v', 'error', '-y', '-filter_complex_threads', '2', *inputs]
            if filters: cmd.extend(filters)
            cmd.extend(['-an', '-frames:v', '257', '-r', '20', '-c:v', 'libx264', '-threads', '4',
                        '-preset', 'veryfast', '-crf', '0' if lossless else '18', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', str(target)])
            subprocess.run(cmd, check=True)
            videos[filename] = validate_video(target, *dimensions)
            part = output / (filename+'.tmp')
            shutil.copyfile(target, part)
            part.replace(output/filename)
        for player, filename in [('alpha','blender_world.mp4'), ('bravo','blender_bravo.mp4')]:
            sequence = sorted((frames/player).glob('frame_*.png'))
            if len(sequence) != 257:
                raise ValueError(f'{name}/{player}: expected 257 rendered PNG files, got {len(sequence)}')
            encode(filename, ['-framerate','20','-start_number','1','-i', str(frames/player/'frame_%04d.png')])
        reference = SOLARIS/'output/solaris'/name/'video_0_side_by_side.mp4'
        for player, y in [('alpha',0),('bravo',352)]:
            encode(f'gt_{player}.mp4', ['-threads','2','-i',str(reference)],
                   ['-vf',f'crop=640:352:0:{y}'], (640,352), lossless=True)
        # Exactly the same composite layout as the previous Solaris page:
        # left column = GT, right column = Blender; top = Alpha, bottom = Bravo.
        graph = ('[0:v]crop=640:704:0:0[gt];'
                 '[1:v]scale=640:352:flags=lanczos[a];[2:v]scale=640:352:flags=lanczos[b];'
                 '[a][b]vstack=inputs=2[world];[gt][world]hstack=inputs=2[out]')
        encode('comparison.mp4', ['-threads','2','-i',str(reference), '-threads','2','-i',str(output/'blender_world.mp4'),
               '-threads','2','-i',str(output/'blender_bravo.mp4')], ['-filter_complex',graph,'-map','[out]'])
        atomic_json(record, {'dataset':name, 'fingerprint':code_hash, 'videos':videos,
            'completed_utc':datetime.now(timezone.utc).isoformat(), 'elapsed_seconds':round(time.monotonic()-started,2),
            'visual_inspection_performed':False})
        if not keep_frames:
            # Remove only intermediates made by the previous single-view draft.
            legacy = output/'frames'
            for p in legacy.glob('frame_*.png'): p.unlink()
            if legacy.exists() and not any(legacy.iterdir()): legacy.rmdir()
        print('VERIFIED', name, '5 videos', round(time.monotonic()-started,1), 'seconds', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', nargs='+', choices=list(SPECS))
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--keep-frames', action='store_true')
    parser.add_argument('--no-publish', action='store_true')
    parser.add_argument('--output-root', type=Path, default=PROJECT / 'outputs')
    parser.add_argument('--spec-file', type=Path, default=PROJECT / 'scene_specs.json')
    parser.add_argument('--site', type=Path)
    args = parser.parse_args()
    names = args.dataset or list(SPECS)
    for name in names: prepare(name)
    with ThreadPoolExecutor(max_workers=max(1, min(args.jobs, len(names)))) as executor:
        futures = [executor.submit(render_one, name, args.force, args.keep_frames,
                                   args.output_root, args.spec_file) for name in names]
        for future in as_completed(futures): future.result()
    if not args.no_publish:
        publish = [__import__('sys').executable, str(PROJECT/'publish_viz.py'),
                   '--output-root', str(args.output_root), '--spec-file', str(args.spec_file)]
        if args.site: publish.extend(['--site', str(args.site)])
        subprocess.run(publish, check=True)


if __name__ == '__main__':
    main()

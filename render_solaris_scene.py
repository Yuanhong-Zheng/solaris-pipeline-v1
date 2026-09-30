"""Blender scenes from image-derived scene specs and sanitized actions only.

No source state trajectories or GT videos are opened by this renderer. Both
cameras observe shared geometry; a lightweight action simulator animates it.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import random
import sys
from pathlib import Path
import bpy
from mathutils import Vector

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))
from motion import FPS, FRAMES, block_events, simulate

SPECS = json.loads((PROJECT / 'scene_specs.json').read_text())
WIDTH, HEIGHT = 1280, 704
PREVIEWS = (1, 86, 172, 257)


def material(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1)
    return mat


def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def move_to(obj, coll):
    for parent in list(obj.users_collection):
        parent.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def empty(name, coll, parent=None, location=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    coll.objects.link(obj)
    obj.parent, obj.location = parent, location
    return obj


def cube(name, pos, size, mat, coll, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj = move_to(bpy.context.object, coll)
    obj.name, obj.parent = name, parent
    obj.location, obj.scale = pos, size
    obj.data.materials.append(mat)
    return obj


def ground(m, world, spec):
    savanna = spec['environment'] == 'savanna'
    cube('Ground to horizon', (0, 0, -.26), (2000, 2000, .5), m['grass'], world)
    # A single mesh of colored tiles keeps a pixelated ground without thousands
    # of separate objects or external texture dependencies.
    rng = random.Random(spec['seed'])
    base = (.28, .30, .07) if savanna else (.16, .29, .055)
    palette = [material(f'Grass pixel {i}', tuple(v * (.70 + i * .07) for v in base)) for i in range(9)]
    verts, faces, indices = [], [], []
    for x in range(-80, 81):
        for y in range(-80, 81):
            n = len(verts)
            px, py, s = x * .5, y * .5, .5
            verts.extend([(px, py, .005), (px+s, py, .005), (px+s, py+s, .005), (px, py+s, .005)])
            faces.append((n, n+1, n+2, n+3))
            indices.append(rng.randrange(len(palette)))
    mesh = bpy.data.meshes.new('Grass tiles')
    mesh.from_pydata(verts, [], faces)
    for mat in palette: mesh.materials.append(mat)
    for poly, idx in zip(mesh.polygons, indices): poly.material_index = idx
    obj = bpy.data.objects.new('Grass tiles', mesh)
    world.objects.link(obj)
    if savanna:
        cube('River channel', (-10, 10, .015), (7, 60, .025), m['water'], world)
        for i in range(12):
            cube(f'River bank {i}', (-6 + .4 * math.sin(i), -16 + i * 5, .1), (1.2, 5, .2), m['dirt'], world)
        # Static terraces remain outside the walking area of the two players.
        for i in range(3):
            cube(f'Savanna terrace {i}', (10 + i * 4, 11, .3 + i * .15), (12, 22, .6 + i*.3), m['grass'], world)
        for i in range(100):
            x, y = rng.uniform(-4, 20), rng.uniform(-14, 26)
            if abs(x) < 1.2 and -1 < y < 6: continue
            cube(f'Tall grass {i}', (x, y, .22), (.10, .16, .44), m['tall'], world)


def tree(x, y, m, world, index):
    cube(f'Acacia trunk {index}', (x, y, 2), (.65, .65, 4), m['bark'], world)
    cube(f'Acacia branch {index}', (x+.8, y, 3.5), (2, .5, .5), m['bark'], world)
    cube(f'Acacia canopy {index}', (x+.5, y, 4.25), (5, 4, .9), m['leaves'], world)
    cube(f'Acacia upper canopy {index}', (x-.4, y+.4, 4.8), (3.5, 3, .4), m['leaves'], world)


def house(x, y, m, world, index):
    cube(f'House {index}', (x, y, 1.8), (4, 4, 3.6), m['wood'], world)
    cube(f'Door {index}', (x, y-2.03, 1), (.9, .08, 2), m['bark'], world)
    for level in range(3):
        cube(f'Roof {index}-{level}', (x, y, 3.8 + .4 * level), (5-level*.9, 5, .45), m['roof'], world)


def environment(spec, m, world):
    ground(m, world, spec)
    # A continuous smooth dome avoids artificial wall seams during full turns.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=400)
    sky = move_to(bpy.context.object, world)
    sky.name = 'Continuous sky dome'
    sky.data.materials.append(m['sky'])
    for poly in sky.data.polygons: poly.use_smooth = True
    rng = random.Random(72)
    for i in range(50):
        cube(f'Cloud {i}', (rng.uniform(-180, 180), rng.uniform(-180, 180), 65),
             (rng.uniform(7, 20), rng.uniform(4, 12), .3), m['cloud'], world)
    if spec['environment'] == 'savanna':
        for i, (x, y) in enumerate([(9, 8), (15, 22), (8, -7), (19, -12), (-18, 29), (27, 35), (-19, -20)]):
            tree(x, y, m, world, i)
    kind = spec['landmarks']
    if kind in ('village_right', 'village_behind'):
        for i in range(5):
            x, y = (7 + 7*i, 55 + 2*i) if kind == 'village_right' else (-12 + 6*i, -65)
            house(x, y, m, world, i)
    if kind in ('sheep', 'distant_animals'):
        for i, (x, y) in enumerate([(-9, 20), (-12, 26), (19, 44)]):
            cube(f'Sheep {i}', (x, y, .72), (.6, 1, .6), m['white'], world)
            cube(f'Sheep head {i}', (x, y-.55, .86), (.36, .36, .42), m['skin'], world)
            for a in (-.22, .22):
                for b in (-.35, .35):
                    cube('Sheep leg', (x+a, y+b, .25), (.16, .16, .5), m['pants'], world)


def avatar(player, states, m, coll):
    root = empty(player + ' body', coll)
    shirt = m['red'] if player == 'alpha' else m['shirt']
    hair = m['blond'] if player == 'alpha' else m['hair']
    cube('Torso', (0, 0, 1.0125), (.45, .25, .675), shirt, coll, root)
    head = empty('Head pivot', coll, root, (0, 0, 1.35))
    cube('Head', (0, 0, .225), (.45, .45, .45), m['skin'], coll, head)
    cube('Hair top', (0, 0, .435), (.47, .47, .12), hair, coll, head)
    cube('Hair back', (0, -.205, .24), (.46, .09, .4), hair, coll, head)
    for side in (-1, 1):
        cube('Eye', (side*.105, .231, .26), (.06, .014, .046), m['shirt'], coll, head)
    limbs = []
    for side in (-1, 1):
        leg = empty('Leg pivot', coll, root, (side*.115, 0, .675))
        cube('Trouser', (0, 0, -.3375), (.215, .25, .675), m['pants'], coll, leg)
        cube('Shoe', (0, .014, -.63), (.22, .28, .09), m['shirt'], coll, leg)
        arm = empty('Arm pivot', coll, root, (side*.34, 0, 1.32))
        cube('Sleeve', (0, 0, -.27), (.22, .26, .54), shirt, coll, arm)
        cube('Cuff', (0, 0, -.40), (.226, .267, .07), m['white'], coll, arm)
        cube('Hand', (0, 0, -.58), (.22, .25, .14), m['skin'], coll, arm)
        limbs.extend([(leg, side), (arm, -side)])
    for frame, state in enumerate(states, 1):
        root.location = state['position']
        root.rotation_euler.z = -state['yaw']
        root.keyframe_insert('location', frame=frame)
        root.keyframe_insert('rotation_euler', frame=frame)
        head.rotation_euler.x = state['pitch']
        head.keyframe_insert('rotation_euler', frame=frame)
        for obj, phase in limbs:
            obj.rotation_euler.x = phase * .5 * math.sin(state['walk_phase']) if state['moving'] else 0
            obj.keyframe_insert('rotation_euler', frame=frame)
    return root


def camera_rig(player, states, m, coll, holding_block):
    data = bpy.data.cameras.new(player + ' camera')
    data.sensor_fit = 'HORIZONTAL'
    data.sensor_width = 36
    data.lens = (36 * HEIGHT / WIDTH) / (2 * math.tan(math.radians(70) / 2))
    data.clip_start, data.clip_end = .03, 1000
    cam = bpy.data.objects.new(player + ' camera', data)
    coll.objects.link(cam)
    cam.rotation_mode = 'QUATERNION'
    arm = empty(player + ' first-person arm', coll, cam, (.60, -.42, -.80))
    arm.rotation_euler = (math.radians(-24), math.radians(-16), math.radians(-14))
    cube('First person sleeve', (0, -.14, 0), (.20, .46, .22), m['red'] if player == 'alpha' else m['shirt'], coll, arm)
    cube('First person cuff', (0, .08, 0), (.205, .07, .225), m['white'], coll, arm)
    cube('First person hand', (0, .17, 0), (.18, .15, .20), m['skin'], coll, arm)
    if holding_block:
        cube('Held stone', (0, .2, -.04), (.35, .35, .35), m['stone'], coll, arm)
    for frame, state in enumerate(states, 1):
        cam.location = Vector(state['position']) + Vector((0, 0, 1.62))
        yaw, pitch = state['yaw'], state['pitch']
        direction = Vector((math.sin(yaw)*math.cos(pitch), math.cos(yaw)*math.cos(pitch), math.sin(pitch)))
        cam.rotation_quaternion = direction.to_track_quat('-Z', 'Y')
        cam.keyframe_insert('location', frame=frame)
        cam.keyframe_insert('rotation_quaternion', frame=frame)
        arm.location.y = -.42 + (.015 * math.sin(state['walk_phase']) if state['moving'] else 0)
        arm.keyframe_insert('location', frame=frame)
    return cam


def configure(scene):
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.fps, scene.render.fps_base = FPS, 1
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.compression = 15
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = int(os.environ.get('BLENDER_THREADS', '8'))
    scene.render.film_transparent = False
    scene.display.render_aa = '8'
    shade = scene.display.shading
    shade.light, shade.studio_light, shade.color_type = 'STUDIO', 'paint.sl', 'MATERIAL'
    shade.show_shadows = False
    shade.show_cavity = True
    shade.cavity_type = 'WORLD'
    shade.background_type, shade.background_color = 'WORLD', (.32, .53, .94)
    scene.world.color = (.32, .53, .94)
    scene.view_settings.view_transform = 'Standard'


def main():
    global SPECS
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True, choices=list(SPECS))
    parser.add_argument('--preview-only', action='store_true')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--frames-dir', type=Path)
    parser.add_argument('--output-root', type=Path, default=PROJECT / 'outputs')
    parser.add_argument('--spec-file', type=Path, default=PROJECT / 'scene_specs.json')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    SPECS = json.loads(args.spec_file.read_text())
    spec = SPECS[args.dataset]
    input_dir = PROJECT / 'inputs' / args.dataset
    condition = json.loads((input_dir / 'condition.json').read_text())
    assert condition['frames'] == FRAMES and condition['fps'] == FPS
    states = {p: simulate(spec['initial'][p], condition['players'][p]['actions']) for p in ('alpha', 'bravo')}
    out = args.output_root / args.dataset
    out.mkdir(exist_ok=True, parents=True)
    frames_dir = args.frames_dir or out / 'frames'
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene_a = bpy.context.scene
    scene_a.name = 'Alpha'
    world = collection('Shared world')
    avatars = {p: collection(p + ' avatar') for p in states}
    rigs = {p: collection(p + ' first person') for p in states}
    colors = {'grass': (.16,.29,.055), 'dirt': (.24,.13,.065), 'water': (.035,.22,.60),
        'tall': (.30,.34,.07), 'bark': (.24,.15,.08), 'leaves': (.18,.22,.04), 'wood': (.47,.29,.10),
        'roof': (.29,.20,.09), 'sky': (.28,.49,.92), 'cloud': (.84,.91,.99), 'white': (.88,.86,.80),
        'shirt': (.022,.018,.023), 'pants': (.038,.022,.055), 'hair': (.017,.039,.083),
        'blond': (.71,.57,.06), 'skin': (.65,.43,.29), 'red': (.63,.024,.015), 'stone': (.31,.33,.32)}
    m = {key: material(key, rgb) for key, rgb in colors.items()}
    environment(spec, m, world)
    for p in states: avatar(p, states[p], m, avatars[p])
    cams = {p: camera_rig(p, states[p], m, rigs[p], args.dataset == 'eval_structure' and p == 'bravo') for p in states}
    events = block_events(states)
    for i, event in enumerate(events):
        obj = cube(f'Placed block {i}', event['position'], (1,1,1), m['stone'], world)
        for frame, hidden in [(1, True), (event['frame'], True), (event['frame']+1, False)]:
            obj.hide_render, obj.hide_viewport = hidden, hidden
            obj.keyframe_insert('hide_render', frame=frame)
            obj.keyframe_insert('hide_viewport', frame=frame)
    scene_b = bpy.data.scenes.new('Bravo')
    scene_b.world = scene_a.world
    for coll in (world, avatars['alpha'], rigs['bravo']): scene_b.collection.children.link(coll)
    scene_a.collection.children.unlink(avatars['alpha'])
    scene_a.collection.children.unlink(rigs['bravo'])
    scenes = {'alpha': scene_a, 'bravo': scene_b}
    for p, scene in scenes.items():
        configure(scene)
        scene.camera = cams[p]
        scene.render.filepath = f'//frames/{p}/frame_'
        scene.frame_set(1)
    # Pack both supplied first images for traceability when opening the .blend.
    for p in states:
        img = bpy.data.images.load(str(input_dir / condition['players'][p]['first_image']))
        img.name = p + ' input first frame'
        img.pack()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.window.scene = scene_a
    bpy.ops.wm.save_as_mainfile(filepath=str(out / f'{args.dataset}.blend'))
    metadata = {'dataset': args.dataset, **{k: spec[k] for k in ('label','category','instruction','environment')},
        'render': {'width': WIDTH, 'height': HEIGHT, 'fps': FPS, 'frames': FRAMES, 'duration': FRAMES/FPS,
            'engine': 'BLENDER_WORKBENCH', 'device': 'CPU (Mesa llvmpipe)', 'views': list(states)},
        'inputs': str(input_dir / 'condition.json'),
        'modeling': {'scene_estimation': (
                'GPT-6 Astra image-conditioned scene layout from Alpha/Bravo first frames and action visualization'
                if spec.get('astra_model') else 'image-derived manual parameters in scene_specs.json'),
            'scene_estimation_model': spec.get('astra_model'),
            'scene_estimation_notes': spec.get('astra_notes', []),
            'gt_poses_used': False, 'future_gt_images_used': False,
            'motion': 'action integration with approximate inertia and Minecraft default movement speeds',
            'camera': '70 degree vertical FOV; eye height 1.62 blocks',
            'limitations': 'Approximate geometry/materials; no Minecraft engine collision reconstruction; placement targets inferred from facing and reach.'},
        'initial_scene': spec['initial'], 'placement_events': events}
    (out / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
    (out / 'simulated_trajectories.json').write_text(json.dumps(states, ensure_ascii=False)+'\n')
    print('SCENE_BUILT', args.dataset, len(bpy.data.objects), flush=True)
    if args.build_only: return
    for p, scene in scenes.items():
        bpy.context.window.scene = scene
        dest = frames_dir / p
        if args.preview_only:
            for frame in PREVIEWS:
                scene.frame_set(frame)
                scene.render.filepath = str(out / f'{p}_preview_{frame:04d}.png')
                bpy.ops.render.render(write_still=True, scene=scene.name)
        else:
            dest.mkdir(exist_ok=True, parents=True)
            for frame in range(1, FRAMES+1):
                scene.frame_set(frame)
                scene.render.filepath = str(dest / f'frame_{frame:04d}.png')
                bpy.ops.render.render(write_still=True, scene=scene.name)
                if frame in PREVIEWS:
                    import shutil
                    shutil.copy2(scene.render.filepath, out / f'{p}_preview_{frame:04d}.png')
                if frame % 64 == 0 or frame == FRAMES: print('RENDER_PROGRESS', args.dataset, p, frame, flush=True)
        print('VIEW_DONE', args.dataset, p, flush=True)


if __name__ == '__main__':
    main()

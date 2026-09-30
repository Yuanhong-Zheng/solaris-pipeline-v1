"""Action-only, deterministic proxy physics; never consumes recorded future poses.

Coordinates: Z is up, initial Alpha looks along +Y. Yaw is clockwise in the
XY plane. Positive Mineflayer yaw turns left, so camera yaw deltas are negated.
Movement speeds use Minecraft defaults, not fitted GT trajectories.
"""
import math

FPS = 20
FRAMES = 257
WALK_SPEED = 4.317
SPRINT_SPEED = 5.612
SNEAK_SPEED = 1.295


def simulate(initial, actions):
    if len(actions) != FRAMES:
        raise ValueError(f'Expected {FRAMES} actions, got {len(actions)}')
    x, y, z = initial['position']
    yaw = initial.get('yaw', 0.0)
    pitch = initial.get('pitch', 0.0)
    vx = vy = vz = distance = 0.0
    floor = z
    states = []
    for i, action in enumerate(actions):
        # Frame 0 is the conditioned image. action[t] drives t -> t+1;
        # action[256] has no following frame in this 257-frame clip.
        states.append(dict(position=[x, y, z], yaw=yaw, pitch=pitch,
                           walk_phase=distance * 2.9, moving=math.hypot(vx, vy) > 0.03,
                           place=bool(action.get('place_block')), action=action))
        dx, dy = action.get('camera', [0, 0])
        yaw -= float(dx)
        pitch = max(-1.5, min(1.5, pitch + float(dy)))
        forward = int(bool(action.get('forward'))) - int(bool(action.get('back')))
        strafe = int(bool(action.get('right'))) - int(bool(action.get('left')))
        norm = max(1.0, math.hypot(forward, strafe))
        speed = SNEAK_SPEED if action.get('sneak') else SPRINT_SPEED if action.get('sprint') else WALK_SPEED
        tx = speed * (forward * math.sin(yaw) + strafe * math.cos(yaw)) / norm
        ty = speed * (forward * math.cos(yaw) - strafe * math.sin(yaw)) / norm
        # Friction/inertia is an explicit approximation, shared across episodes.
        vx += (tx - vx) * 0.55
        vy += (ty - vy) * 0.55
        if abs(vx) < 0.001: vx = 0.0
        if abs(vy) < 0.001: vy = 0.0
        x += vx / FPS
        y += vy / FPS
        distance += math.hypot(vx, vy) / FPS
        if action.get('jump') and z <= floor + 1e-5:
            vz = 8.4
        z += vz / FPS
        vz -= 32.0 / FPS
        if z <= floor:
            z = floor
            vz = 0.0
    return states


def block_events(trajectories):
    """Place solid unit cubes on a shared, persistent integer grid.

    The action file has no target block coordinate, so target inference uses
    the actor's simulated facing direction and a 2.5 block reach. Repeated
    rising edges at an occupied column stack upwards.
    """
    candidates = []
    for player, states in trajectories.items():
        previous = False
        for frame, state in enumerate(states):
            active = state['place']
            if active and not previous and frame + 1 < FRAMES:
                x, y, z = state['position']
                yaw = state['yaw']
                cell = (math.floor(x + 2.5 * math.sin(yaw)), math.floor(y + 2.5 * math.cos(yaw)))
                candidates.append((frame + 1, player, cell))
            previous = active
    events, heights = [], {}
    for frame, player, cell in sorted(candidates):
        level = heights.get(cell, 0)
        events.append(dict(player=player, frame=frame,
                           position=[cell[0] + 0.5, cell[1] + 0.5, level + 0.5]))
        heights[cell] = level + 1
    return events

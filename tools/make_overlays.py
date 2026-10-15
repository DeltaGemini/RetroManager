"""
Writes the touch-control layouts for systems that didn't come with one
(frontend/overlays/rm_*.cfg), in the style and at the positions of the
hand-made ones beside them (rm_gba.cfg, rm_snes.cfg, rm_nds.cfg, rm_nds_mid.cfg:
this doesn't write those): the same D-pad,
thumbstick, shoulder and system buttons, with each system's own face buttons.
They're RetroArch overlay files like the others, so they can be edited by hand
afterwards; running this again overwrites them.

    python tools/make_overlays.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'frontend' / 'overlays'

# (x, y, shape, rx, ry) for each orientation, from the hand-made layouts
LAND = {
    'dpad': [('left', 0.0671, 0.41869, 'radial', 0.04, 0.08667, 'dpad-left.png'), ('right', 0.17268, 0.41869, 'radial', 0.04, 0.08667, 'dpad-right.png'),
             ('up', 0.12037, 0.30731, 'radial', 0.04, 0.08667, 'dpad-up.png'), ('down', 0.12037, 0.52979, 'radial', 0.04, 0.08667, 'dpad-down.png'),
             ('left|up', 0.05645, 0.28213, 'rect', 0.02479, 0.0537, None), ('right|up', 0.18527, 0.27922, 'rect', 0.02479, 0.0537, None),
             ('left|down', 0.05548, 0.55817, 'rect', 0.02479, 0.0537, None), ('right|down', 0.18333, 0.5572, 'rect', 0.02479, 0.05371, None)],
    'stick': (0.11601, 0.41, 0.09, 0.195, 1.5),
    'two': {'a': (0.92, 0.34, 0.05, 0.10833), 'b': (0.87, 0.56, 0.05, 0.10833)},
    'four': {'a': (0.94719, 0.42216, 0.04, 0.08667), 'b': (0.88973, 0.55986, 0.04, 0.08667), 'x': (0.88973, 0.27852, 0.04, 0.08667), 'y': (0.8293, 0.42216, 0.04, 0.08667)},
    # Three across, two rows (Mega Drive)
    'six': {'col': (0.80, 0.875, 0.95), 'row': (0.33, 0.52), 'r': (0.036, 0.078)},
    'start': (0.92622, 0.88551, 0.03248, 0.07388), 'select': (0.10597, 0.88551, 0.03334, 0.07388),
    'l': (0.02933, 0.7, 0.04273, 0.09259), 'r': (0.97368, 0.7, 0.04273, 0.09259),
    'small': (0.02137, 0.04629),
    'menu': (0.05, 0.08889), 'save': (0.106, 0.0889), 'fast': (0.89, 0.08889), 'exit': (0.95, 0.08889), 'switch': (0.03979, 0.88228),
}
PORT = {
    'dpad': [('left', 0.12624, 0.66015, 'radial', 0.0963, 0.03984, 'dpad-left.png'), ('right', 0.35664, 0.66015, 'radial', 0.0963, 0.03984, 'dpad-right.png'),
             ('up', 0.24074, 0.60476, 'radial', 0.08241, 0.04427, 'dpad-up.png'), ('down', 0.24074, 0.71553, 'radial', 0.08241, 0.04427, 'dpad-down.png'),
             ('left|up', 0.1063, 0.5959, 'rect', 0.0537, 0.02479, None), ('right|up', 0.38101, 0.5959, 'rect', 0.0537, 0.02479, None),
             ('left|down', 0.1063, 0.72439, 'rect', 0.0537, 0.02479, None), ('right|down', 0.38101, 0.72439, 'rect', 0.0537, 0.02479, None)],
    'stick': (0.24004, 0.64962, 0.2, 0.09231, 2.0),
    'two': {'a': (0.85, 0.6, 0.08858, 0.04088), 'b': (0.68009, 0.66679, 0.08858, 0.04088)},
    'four': {'a': (0.85493, 0.64842, 0.08858, 0.04088), 'b': (0.71659, 0.71559, 0.08858, 0.04088), 'x': (0.71659, 0.58126, 0.08858, 0.04088), 'y': (0.57725, 0.64842, 0.08858, 0.04088)},
    'six': {'col': (0.577, 0.716, 0.855), 'row': (0.605, 0.685), 'r': (0.066, 0.0305)},
    'start': (0.6, 0.5, 0.07037, 0.03374), 'select': (0.4, 0.5, 0.07037, 0.03374),
    'l': (0.04815, 0.45, 0.09259, 0.04273), 'r': (0.95185, 0.45, 0.09259, 0.04273),
    'small': (0.04633, 0.02137),
    'menu': (0.5, 0.9), 'save': (0.3, 0.9), 'fast': (0.6, 0.85), 'exit': (0.7, 0.9), 'switch': (0.4, 0.85),
}


def overlay(name, side, descs):
    lines = [('name', f'"{name}"'), ('full_screen', 'true'), ('normalized', 'true'), ('range_mod', '1.5'), ('alpha_mod', '2.0'),
             ('aspect_ratio', '2.1666667' if side is LAND else '0.4615385'), ('descs', str(len(descs)))]
    for i, d in enumerate(descs):
        name_, x, y, shape, rx, ry, image = d[:7]
        lines.append((f'desc{i}', f'"{name_},{x:.5f},{y:.5f},{shape},{rx:.5f},{ry:.5f}"'))
        if image:
            lines.append((f'desc{i}_overlay', image))
        for key, value in (d[7] if len(d) > 7 else {}).items():
            lines.append((f'desc{i}_{key}', value))
    return lines


def movement(side, stick):
    if not stick:
        return list(side['dpad'])
    x, y, rx, ry, reach = side['stick']
    return [('null', x, y, 'radial', rx, ry, 'thumbstick-background.png'),
            ('analog_left', x, y, 'radial', rx, ry, 'thumbstick-pad_arcade.png', {'range_mod': str(reach), 'saturate_pct': '0.65', 'movable': 'true'})]


def system_buttons(side, prefix, stick, stick_first):
    rx, ry = side['small']
    # The button that swaps the D-pad for the thumbstick and back
    other = '' if stick != stick_first else ('-dpad' if stick_first else '-analog')
    return [('menu_toggle', *side['menu'], 'radial', rx, ry, 'rgui.png'), ('save_state', *side['save'], 'radial', rx, ry, 'save.png'),
            ('toggle_fast_forward', *side['fast'], 'radial', rx, ry, 'fast_forward.png'), ('exit_emulator', *side['exit'], 'radial', rx, ry, 'Exit.png'),
            ('overlay_next', *side['switch'], 'radial', rx, ry, 'digital.png' if stick else 'analog.png', {'next_target': f'"{prefix}{other}"'})]


def write(name, build, stick_first=False):
    """build(side, portrait) -> the system's own buttons. Four overlays: each
    orientation with the D-pad and with the thumbstick (first for a system that
    needs one), which the small button swaps between."""
    overlays = []
    for side, prefix in ((LAND, 'landscape'), (PORT, 'portrait')):
        for stick in ((True, False) if stick_first else (False, True)):
            suffix = '' if stick == stick_first else ('-dpad' if stick_first else '-analog')
            overlays.append(overlay(prefix + suffix, side, movement(side, stick) + build(side, side is PORT) + system_buttons(side, prefix, stick, stick_first)))
    text = [f'overlays = {len(overlays)}']
    for i, lines in enumerate(overlays):
        text += [f'overlay{i}_{key} = {value}' for key, value in lines]
    (OUT / f'rm_{name}.cfg').write_text('\n'.join(text) + '\n')


def face(side, kind, images):
    return [(button, *side[kind][button][:2], 'radial', *side[kind][button][2:], image) for button, image in images.items()]


def rect(side, key, name, image, x=None, y=None):
    px, py, rx, ry = side[key]
    return (name, px if x is None else x, py if y is None else y, 'rect', rx, ry, image)


def nes(side, portrait):
    return face(side, 'two', {'a': 'A.png', 'b': 'B.png'}) + [rect(side, 'start', 'start', 'start.png'), rect(side, 'select', 'select', 'start.png')]


def sms(side, portrait):
    # Button 1 is the pad's B, button 2 its A
    return face(side, 'two', {'a': '2.png', 'b': '1.png'}) + [rect(side, 'start', 'start', 'start.png')]


def megadrive(side, portrait):
    # As Genesis Plus GX has them: A B C are the pad's Y B A, and X Y Z its L X R
    cols, rows, (rx, ry) = side['six']['col'], side['six']['row'], side['six']['r']
    grid = [('l', 'X.png'), ('x', 'Y.png'), ('r', 'Z.png')], [('y', 'A.png'), ('b', 'B.png'), ('a', 'C.png')]
    buttons = [(button, cols[c], rows[r], 'radial', rx, ry, image) for r, row in enumerate(grid) for c, (button, image) in enumerate(row)]
    return buttons + [rect(side, 'start', 'start', 'start.png'), rect(side, 'select', 'select', 'start.png')]


def psx(side, portrait):
    buttons = face(side, 'four', {'a': 'circle.png', 'b': 'cross.png', 'x': 'triangle.png', 'y': 'square.png'})
    if portrait:
        shoulders = [('l', 0.09, 0.45, 'rect', 0.08, 0.037, 'L1.png'), ('l2', 0.26, 0.45, 'rect', 0.08, 0.037, 'L2.png'),
                     ('r', 0.91, 0.45, 'rect', 0.08, 0.037, 'R1.png'), ('r2', 0.74, 0.45, 'rect', 0.08, 0.037, 'R2.png')]
        middle = [rect(side, 'start', 'start', 'start_psx.png', y=0.513), rect(side, 'select', 'select', 'select_psx.png', y=0.513)]
    else:
        shoulders = [('l', 0.02933, 0.655, 'rect', 0.04, 0.047, 'L1.png'), ('l2', 0.02933, 0.757, 'rect', 0.04, 0.047, 'L2.png'),
                     ('r', 0.97368, 0.655, 'rect', 0.04, 0.047, 'R1.png'), ('r2', 0.97368, 0.757, 'rect', 0.04, 0.047, 'R2.png')]
        middle = [rect(side, 'start', 'start', 'start_psx.png'), rect(side, 'select', 'select', 'select_psx.png')]
    return buttons + shoulders + middle


def n64(side, portrait):
    # As Mupen64Plus has them: A and B are the pad's B and Y, Z its L2, and the C
    # buttons the right stick's four directions
    if portrait:
        c = [('r_y_minus', 0.80, 0.529, 'c_up.png'), ('r_y_plus', 0.80, 0.621, 'c_down.png'), ('r_x_minus', 0.70, 0.575, 'c_left.png'), ('r_x_plus', 0.90, 0.575, 'c_right.png')]
        return [(name, x, y, 'radial', 0.058, 0.0268, image) for name, x, y, image in c] + [
            ('b', 0.80, 0.703, 'radial', 0.08858, 0.04088, 'A.png'), ('y', 0.61, 0.665, 'radial', 0.078, 0.036, 'B.png'),
            ('l2', 0.27, 0.45, 'radial', 0.08, 0.037, 'Z.png'), rect(side, 'l', 'l', 'L.png'), rect(side, 'r', 'r', 'R.png'),
            rect(side, 'start', 'start', 'start.png', x=0.5)]
    c = [('r_y_minus', 0.905, 0.2025, 'c_up.png'), ('r_y_plus', 0.905, 0.3975, 'c_down.png'), ('r_x_minus', 0.86, 0.30, 'c_left.png'), ('r_x_plus', 0.95, 0.30, 'c_right.png')]
    return [(name, x, y, 'radial', 0.028, 0.0607, image) for name, x, y, image in c] + [
        ('b', 0.93, 0.62, 'radial', 0.045, 0.0975, 'A.png'), ('y', 0.835, 0.52, 'radial', 0.04, 0.08667, 'B.png'),
        ('l2', 0.118, 0.7, 'radial', 0.04, 0.08667, 'Z.png'), rect(side, 'l', 'l', 'L.png'), rect(side, 'r', 'r', 'R.png', y=0.84),
        rect(side, 'select', 'start', 'start.png')]


if __name__ == '__main__':
    write('nes', nes)
    write('sms', sms)
    write('megadrive', megadrive)
    write('psx', psx)
    write('n64', n64, stick_first=True)
    print('Wrote', ', '.join(sorted(p.name for p in OUT.glob('rm_*.cfg'))))

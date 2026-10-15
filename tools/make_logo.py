"""
Draws RetroManager's name as a logo (frontend/open/retromanager-logo.svg), for
a copy that's given to others: the header's logo in the Switch themes
(frontend/themes/switch/retromanager-logo.svg) is lettered in a Sega logo
font, which isn't ours to pass on.

This one is blocks on a grid: each letter a 5 by 7 pattern of our own (below),
heavy and leaning a little, in the same orange-to-purple. No font is involved.
RetroManager uses it wherever the other isn't there, and always when
OPEN_ARTWORK=1 (backend/routes/pages.py).

    python tools/make_logo.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'frontend' / 'open' / 'retromanager-logo.svg'

LETTERS = {
    'R': ['11110', '10001', '10001', '11110', '10100', '10010', '10001'],
    'E': ['11111', '10000', '10000', '11110', '10000', '10000', '11111'],
    'T': ['11111', '00100', '00100', '00100', '00100', '00100', '00100'],
    'O': ['01110', '10001', '10001', '10001', '10001', '10001', '01110'],
    'M': ['10001', '11011', '10101', '10101', '10001', '10001', '10001'],
    'A': ['01110', '10001', '10001', '11111', '10001', '10001', '10001'],
    'N': ['10001', '11001', '10101', '10011', '10001', '10001', '10001'],
    'G': ['01110', '10001', '10000', '10111', '10001', '10001', '01110'],
}
CELL = 10        # a square of the grid
WIDE = 1.75      # each filled square is this many wide, so the strokes are heavy enough to read small
STEP = 7         # from one letter's start to the next, in squares
LEAN = 0.2       # how far each row up shifts right, in squares
# The words, and where each starts on the grid (the second set in, under the first)
WORDS = [('RETRO', 0, 0), ('MANAGER', 10, 8.4)]


def main():
    squares = []
    for word, left, top in WORDS:
        for i, letter in enumerate(word):
            for row, line in enumerate(LETTERS[letter]):
                for col, on in enumerate(line):
                    if on == '1':
                        # (leaning: the higher the row on the whole logo, the further right)
                        x = (left + i * STEP + col + (15.4 - (top + row)) * LEAN) * CELL
                        squares.append(f'<rect x="{x:.1f}" y="{(top + row) * CELL:.1f}" width="{WIDE * CELL:.1f}" height="{CELL + 0.3}"/>')
    width = round((10 + 6 * STEP + 4 + WIDE + 15.4 * LEAN) * CELL)
    height = round(15.4 * CELL)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="RetroManager">
  <!-- RetroManager's name in squares on a grid (tools/make_logo.py): no font, nobody's lettering -->
  <defs>
    <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{width}" y2="{height}">
      <stop offset="0" stop-color="#ff6a1f"/>
      <stop offset="0.5" stop-color="#e0507c"/>
      <stop offset="1" stop-color="#a63fd0"/>
    </linearGradient>
  </defs>
  <g fill="url(#g)">
    {''.join(squares)}
  </g>
</svg>
''', encoding='utf-8')
    print(f"Wrote {OUT} ({width} x {height}, {len(squares)} squares)")


if __name__ == '__main__':
    main()

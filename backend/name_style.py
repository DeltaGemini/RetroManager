"""
House style for game names, used by Scan → "Names not in house style", by
scraping and by "Create entries":

    Star Wars - Rogue Leader - Rogue Squadron II  ->  Star Wars: Rogue Leader - Rogue Squadron II
    Legend of Zelda, The - Skyward Sword          ->  The Legend of Zelda: Skyward Sword
    Animal Crossing - City Folk (USA) (Rev 1)     ->  Animal Crossing: City Folk
    MARIO KART 7                                  ->  Mario Kart 7
    Pokemon - Emerald Version                     ->  Pokémon: Emerald Version

Rules, in order:
  1. Remove file tags: [anything], and (…) holding only regions, languages,
     revisions or versions. Other brackets, like "(Disc 1)", stay.
  2. Tidy spaces, and " : " (ScreenScraper's French-style colon) becomes ": ".
  3. A trailing ", The" / ", A" / ", An" on the first part moves to the front.
  4. A series name followed by a subtitle and then " - " gets its colon:
     "Star Wars Episode I - Racer" -> "Star Wars: Episode I - Racer".
     Only when a " - " follows, so "Batman Returns" is left alone, and not for
     sequels ("Castlevania II - …") or "Harry Potter and the…". The Legend of
     Zelda always gets one: "The Legend of Zelda: The Minish Cap".
  5. Otherwise, if there's no colon yet, the first " - " becomes ": ".
  6. Title Case: small words (of, the, and…) lower case except at the start
     of a part; words already in capitals or mixed case (NBA, II, WarioWare)
     are kept, unless the whole name was in capitals.
  7. Pokemon -> Pokémon.

Extra series names can be added with the NAME_STYLE_SERIES environment
variable (comma separated).
"""

import os
import re

SERIES = [
    'Star Wars', 'Star Trek', 'The Legend of Zelda', 'Harry Potter', 'Batman',
    'Lego Star Wars', 'LEGO Star Wars', 'Castlevania', 'Mega Man', 'Kirby',
    'Metroid', 'Donkey Kong Country', 'Final Fantasy', 'Kingdom Hearts',
    'Spider-Man', 'Tom Clancy\'s', 'Disney\'s',
]
SERIES += [s.strip() for s in os.environ.get('NAME_STYLE_SERIES', '').split(',') if s.strip()]
# Longest first so "Lego Star Wars" wins over "Star Wars"
SERIES = sorted(set(SERIES), key=len, reverse=True)

SMALL_WORDS = {
    'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'of', 'on', 'in', 'at',
    'to', 'by', 'as', 'vs', 'vs.', 'via', 'per', "'n", 'no',
}
ARTICLES = {'the', 'a', 'an'}
# "Disney The Princess and the Frog": the article starts the real title
BRANDS = {'disney', 'pixar', 'disney-pixar', 'dreamworks'}
# Series that always take a colon, even without a later " - "
ALWAYS_COLON = {'the legend of zelda'}
_ROMAN_RE = re.compile(r'^[IVXLC]+$')
# Kept in capitals when converting an ALL CAPS name
ACRONYMS = {
    'II', 'III', 'IV', 'VI', 'VII', 'VIII', 'IX', 'XI', 'XII', 'XIII', 'XIV', 'XV',
    'NBA', 'NFL', 'NHL', 'FIFA', 'WWE', 'WWF', 'WCW', 'UFC', 'TMNT', 'NASCAR',
    'DS', '3DS', 'HD', 'XL', 'EX', 'DX', 'GP', 'RPG', 'USA', 'UK', 'TV', 'CD',
}

_REGIONS = {
    'usa', 'us', 'europe', 'eu', 'japan', 'jp', 'world', 'asia', 'australia',
    'korea', 'uk', 'france', 'germany', 'spain', 'italy', 'netherlands', 'sweden',
    'brazil', 'canada', 'china', 'taiwan', 'hong kong', 'russia', 'scandinavia',
    'ntsc', 'pal', 'ntsc-u', 'ntsc-j', 'pal-e', 'unl', 'beta', 'proto', 'demo',
    'sample', 'virtual console', 'aftermarket', 'wiiware',
    # GoodTools region letters
    'e', 'u', 'j', 'w', 'ue', 'ju', 'uj', 'a', 'k', 'f', 'g',
}
# 3DS/DS product codes: CTR-P-AKHP, TWL-N-ABCD
_PRODUCT_CODE_RE = re.compile(r'^(?:CTR|KTR|TWL|NTR|RVL|DOL)-[A-Z]-[A-Z0-9]{4}$')
_LANG_RE = re.compile(r'^[A-Z][a-z](?:-[A-Z][a-z]+)?$')        # En, Fr, Pt-BR
_VERSION_RE = re.compile(r'^(?:rev\s*\w+|v\s?\d[\w.]*|r\d+)$', re.IGNORECASE)
_PAREN_RE = re.compile(r'\s*\(([^()]*)\)')
_BRACKET_RE = re.compile(r'\s*\[[^\[\]]*\]')
_ARTICLE_RE = re.compile(r'^(?P<body>[^:]+?),\s+(?P<art>The|A|An)(?P<rest>(?:\s*(?::|\s-\s|\().*)?)$', re.IGNORECASE)
_POKEMON_RE = re.compile(r'\bpokemon\b', re.IGNORECASE)


def _is_tag(content: str) -> bool:
    parts = [p.strip() for p in content.split(',')]
    return bool(parts) and all(
        p and (p.lower() in _REGIONS or _LANG_RE.match(p) or _VERSION_RE.match(p)
               or _PRODUCT_CODE_RE.match(p))
        for p in parts
    )


def strip_tags(name: str) -> str:
    name = _BRACKET_RE.sub('', name)
    return _PAREN_RE.sub(lambda m: '' if _is_tag(m.group(1)) else m.group(0), name)


def _cap_first(word: str) -> str:
    # Only a leading letter, after any quotes/brackets: "25th" stays as is
    for i, ch in enumerate(word):
        if ch.isalpha():
            return word[:i] + ch.upper() + word[i + 1:]
        if ch.isalnum():
            return word
    return word


def _style_word(word: str, first: bool, all_caps: bool, prev: str = '') -> str:
    bare = word.strip('.,!?:;()"\'')
    if any('\u2160' <= ch <= '\u2188' for ch in bare) or re.match(r'^v\d', bare):
        return word  # Ⅳ, v1
    if all_caps:
        if bare in ACRONYMS or any(ch.isdigit() for ch in bare) and bare.isupper():
            return word
        word = word.lower()
    elif any(ch.isupper() for ch in word[1:]) or (word[:1].isupper() and word.lower() not in SMALL_WORDS):
        return word  # already capitalised, an acronym, or mixed case (WarioWare)
    if word.lower() in ARTICLES and word[:1].isupper() and (prev.lower() in BRANDS or prev.endswith("'s")):
        return word
    if not first and word.lower() in SMALL_WORDS:
        return word.lower()
    # Spider-man -> Spider-Man
    return '-'.join(_cap_first(part) for part in word.split('-'))


def title_case(name: str) -> str:
    letters = [ch for ch in name if ch.isalpha()]
    all_caps = len(letters) >= 4 and all(ch.isupper() for ch in letters)
    words = name.split(' ')
    out = []
    first = True
    for i, word in enumerate(words):
        if not word:
            continue
        if word in ('-', ':', '&'):
            out.append(word)
            first = word != '&'
            continue
        last = i == len(words) - 1
        styled = _style_word(word, first or last, all_caps, out[-1] if out else '')
        out.append(styled)
        # A new part starts after "Title:" or an opening bracket
        first = word.endswith(':') or word.endswith('(')
    return ' '.join(out)


def _apply_series(name: str) -> str:
    """"Star Wars Episode I - Racer" -> "Star Wars: Episode I - Racer"."""
    for series in SERIES:
        if not name.lower().startswith(series.lower() + ' '):
            continue
        rest = name[len(series) + 1:]
        if rest.startswith(('-', ':', '&', '(')):
            return name
        if series.lower() not in ALWAYS_COLON:
            # Needs a subtitle of two or more words before a " - ", and not a
            # sequel number or "and the…": "Castlevania II - …", "Harry Potter and…"
            if ' - ' not in rest:
                return name
            head = rest.split(' - ', 1)[0].split()
            if len(head) < 2 or head[0].lower() in SMALL_WORDS or head[0] == '&':
                return name
        if (rest.split() or [''])[0].isdigit() or _ROMAN_RE.match((rest.split() or [''])[0]):
            return name
        return name[:len(series)] + ': ' + rest
    return name


def style_name(name: str) -> str:
    """The house-style version of a game name (may be unchanged)."""
    if not name:
        return name
    styled = strip_tags(name)
    styled = re.sub(r'\s+', ' ', styled).strip()
    styled = re.sub(r'\s+:\s*', ': ', styled)
    styled = re.sub(r'\s*-\s*$', '', styled)

    match = _ARTICLE_RE.match(styled)
    if match:
        styled = f"{match['art'].capitalize()} {match['body'].strip()}{match['rest']}"

    if ':' not in styled:
        styled = _apply_series(styled)
    if ':' not in styled and ' - ' in styled:
        styled = styled.replace(' - ', ': ', 1)

    styled = title_case(styled)
    styled = _POKEMON_RE.sub(lambda m: 'POKÉMON' if m.group(0).isupper() else 'Pokémon', styled)
    return styled or name

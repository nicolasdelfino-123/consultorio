import re
import unicodedata

_VOWELS = {'a': 'aá', 'e': 'eé', 'i': 'ií', 'o': 'oó', 'u': 'uúü'}
_TRANSLATION = str.maketrans('áéíóúü', 'aeiouu')


def term_key(term):
    """Spanish accent-insensitive key; ñ remains distinct from n."""
    return unicodedata.normalize('NFC', term.strip()).casefold().translate(_TRANSLATION)


def _term_pattern(term):
    parts = []
    for character in unicodedata.normalize('NFC', term):
        base = character.lower().translate(_TRANSLATION)
        if base in _VOWELS:
            # Accept precomposed and decomposed accents without altering the
            # rest of the transcript or offsets used by re.sub.
            parts.append('[' + _VOWELS[base] + '][\u0301\u0308]*')
        elif character.lower() == 'ñ':
            parts.append('(?:ñ|n\u0303)')
        else:
            parts.append(re.escape(character))
    return ''.join(parts)


def protect(text, rules):
    """Whole terms, Spanish accent/case-insensitive, longest first, no cascading."""
    terms = [(term.strip(), replacement) for term, replacement in rules if term.strip()]
    if not terms:
        return text
    terms.sort(key=lambda item: len(unicodedata.normalize('NFC', item[0])), reverse=True)
    replacements = {f'r{index}': replacement for index, (_, replacement) in enumerate(terms)}
    boundary = r'[\w\u0300-\u036f]'
    pattern = '(?<!' + boundary + ')(?:' + '|'.join(
        f'(?P<r{index}>{_term_pattern(term)})' for index, (term, _) in enumerate(terms)
    ) + ')(?!' + boundary + ')'
    return re.sub(pattern, lambda match: replacements[match.lastgroup], text, flags=re.IGNORECASE)

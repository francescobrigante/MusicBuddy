# ==================================================================
# Music Theory Utility Functions
# ==================================================================

import re
from typing import Tuple, List, Dict, Optional
from src.utils.logger import setup_logger
from src.config import NOTES, FLAT_TO_SHARP, ROMAN_TO_SEMITONE, INTERVAL_TO_ROMAN, MINOR_QUALITIES, DIMINISHED_QUALITIES, SUFFIX_MAP

logger = setup_logger()

def normalize_note(note: str) -> str:
    """Normalizes note name to sharp notation (e.g., Bb -> A#)."""
    return FLAT_TO_SHARP.get(note, note)

def roman_to_chord(tonic: str, roman: str) -> Tuple[str, str]:
    """Converts Roman numeral to (Root, Quality) tuple."""
    match = re.match(r'^(VII|VI|V|IV|III|II|I|vii|vi|v|iv|iii|ii|i)([b#]?)(°?)(.*)$', roman)
    
    if not match:
        logger.error(f"[ERROR] Invalid Roman numeral: {roman} in roman_to_chord()")
        return (tonic, 'major') # Fallback

    numeral, accidental, degree_sym, suffix = match.groups()
    
    # Reconstruct base for semitone lookup (Numeral + Accidental)
    base_roman = numeral + accidental

    # 1. Determine base quality
    if base_roman in ROMAN_TO_SEMITONE:
        interval = ROMAN_TO_SEMITONE[base_roman]
        if degree_sym == '°':
            quality = 'dim'
        elif numeral.islower(): 
            quality = 'minor'
        else:
            quality = 'major'
    else:
        logger.error(f"[ERROR] Invalid Roman numeral: {roman} in roman_to_chord() - unknown numeral: {base_roman}")
        return (tonic, 'major') # Fallback

    # 2. Determine Root
    try:
        tonic_idx = NOTES.index(normalize_note(tonic))
    except ValueError:
        tonic_idx = 0 # Default to C
        
    root_idx = (tonic_idx + interval) % 12
    root_note = NOTES[root_idx]
    
    # 3. Determine Final Quality based on base quality + suffix
    final_quality = quality
    
    if suffix == '7':
        if quality == 'major': final_quality = '7'            # C 7 -> C7
        elif quality == 'minor': final_quality = 'm7'     # Cminor7 -> Cm7
        elif quality == 'dim': final_quality = 'dim7'         # C°7 -> Cdim7

    else:
        # Use suffix map to get right quality
        if suffix in SUFFIX_MAP:
            final_quality = SUFFIX_MAP[suffix]
        
        # If no suffix, keep base quality (major/minor/dim)
        elif not suffix:
            final_quality = quality
            
        else:
            logger.error(f"[ERROR] Unknown quality: {quality} (suffix='{suffix}') in roman_to_chord()")
            final_quality = 'major'
        
    return (root_note, final_quality)


def chord_to_roman(tonic: str, root: str, quality: str) -> str:
    """Converts (Root, Quality) to Roman numeral relative to Tonic."""
    try:
        tonic_idx = NOTES.index(normalize_note(tonic))
        root_idx = NOTES.index(normalize_note(root))
    except ValueError:
        return 'I'

    interval = (root_idx - tonic_idx) % 12
    
    # Use chromatic map for base roman
    base_roman = INTERVAL_TO_ROMAN.get(interval, 'I')
    
    # Split accidental from numeral (Trailing)
    accidental = ''
    if base_roman.endswith('b') or base_roman.endswith('#'):
        accidental = base_roman[-1]
        numeral = base_roman[:-1]
    else:
        numeral = base_roman
    
    # Determine case (upper/lower)
    if quality in MINOR_QUALITIES:
        base_numeral = numeral.lower() + accidental
    else:
        base_numeral = numeral.upper() + accidental

    suffix = SUFFIX_MAP.get(quality, '')
    return base_numeral + suffix

def compact_chord(root: str, quality: str) -> str:
    """Returns compact string representation (e.g., 'Am', 'Cmaj7')."""
    suffix = ''
    if quality == 'minor': suffix = 'm'
    elif quality == 'dim': suffix = '°'
    elif quality == 'aug': suffix = '+'
    elif quality == 'm7': suffix = 'm7'
    elif quality == 'm7b5': suffix = 'm7b5'
    elif quality == 'msus2': suffix = 'msus2'
    elif quality == 'msus4': suffix = 'msus4'
    elif quality != 'major': suffix = quality
    return f"{root}{suffix}"

def parse_compact_chord(chord_str: str) -> Tuple[str, str]:
    """Parses compact string (e.g., 'Cm7', 'Cmaj7') into (Root, Quality)."""
    match = re.match(r'^([A-G][#b]?)(.*)$', chord_str)
    if not match: 
        logger.error(f"[ERROR] Invalid compact chord: {chord_str} in parse_compact_chord()")
        return (chord_str, 'major')
    
    root, q_str = match.groups()
    
    # Handle case-sensitive cases first (M vs m)
    if q_str == 'M7': return (root, 'maj7')
    if q_str == 'M': return (root, 'major')
    
    # Normalize suffix for robustness
    q_str_lower = q_str.lower()
    
    if q_str_lower in ['', 'maj', 'major']:
        quality = 'major'
    elif q_str_lower in ['m', 'min', 'minor', '-']:
        quality = 'minor'
    elif q_str_lower in ['7', 'dom7']:
        quality = '7'
    elif q_str_lower in ['maj7', 'major7', 'j7']:
        quality = 'maj7'
    elif q_str_lower in ['m7', 'min7', 'minor7', '-7']:
        quality = 'm7'
    elif q_str_lower in ['m9', 'min9', 'minor9', '-9']:
        quality = 'm9'
    elif q_str_lower in ['m11', 'min11', 'minor11', '-11']:
        quality = 'm11'
    elif q_str_lower in ['m13', 'min13', 'minor13', '-13']:
        quality = 'm13'
    elif q_str_lower in ['dim', 'o', '0']:
        quality = 'dim'
    elif q_str_lower in ['dim7', 'o7', '07']:
        quality = 'dim7'
    elif q_str_lower in ['m7b5', 'h7', 'halfdim', 'half_dim7', '-7b5']:
        quality = 'm7b5'
    elif q_str_lower in ['aug', '+', 'aug5']:
        quality = 'aug'
    elif q_str_lower in ['sus2']:
        quality = 'sus2'
    elif q_str_lower in ['sus4', 'sus']:
        quality = 'sus4'
    elif q_str_lower in ['6', 'maj6', 'major6']:
        quality = '6'
    elif q_str_lower in ['m6', 'min6', 'minor6', '-6']:
        quality = 'minor6'
    elif q_str_lower in ['add9', 'add2']:
        quality = 'add9'
    elif q_str_lower in ['9', 'dom9']:
        quality = '9'
    elif q_str_lower in ['11', 'dom11']:
        quality = '11'
    elif q_str_lower in ['13', 'dom13', '13b']:
        quality = '13'
    elif q_str_lower in ['maj9']:
        quality = 'maj9'
    elif q_str_lower in ['maj11']:
        quality = 'maj11'
    elif q_str_lower in ['maj13']:
        quality = 'maj13'
    elif q_str_lower in ['msus2', 'm(sus2)', 'minorsus2', '-sus2', 'minsus2']:
        quality = 'msus2' 
    elif q_str_lower in ['msus4', 'm(sus4)', 'minorsus4', '-sus4', 'minsus4', 'msus', 'minsus']:
        quality = 'msus4'
    else:
        quality = 'major'  # Default fallback
        
    return (root, quality)

def progression_to_chords(tonic: str, progression: List[str]) -> List[Tuple[str, str]]:
    """Converts list of Roman numerals to list of (Root, Quality)."""
    return [roman_to_chord(tonic, r) for r in progression]

def roman_to_compact(tonic: str, roman: str) -> str:
    """Helper to get readable chord name from Roman numeral (e.g. 'I' -> 'C' in C major)."""
    try:
        root, c_type = roman_to_chord(tonic, roman)
        name = compact_chord(root, c_type)
        return name
    except:
        return roman

def get_top_k(probs: Dict[str, float], k: int = 5) -> List[Tuple[str, float]]:
    """Returns top k items from a probability dictionary."""
    return sorted(probs.items(), key=lambda item: item[1], reverse=True)[:k]

def format_distribution(dist_items: List[Tuple[str, float]], key: str) -> str:
    """Formats distribution items into a readable string: 'Name (Roman): Prob'."""
    formatted = []
    for roman, p in dist_items:
        try:
            name = roman_to_compact(key, roman)
            formatted.append(f"{name} ({roman}): {p:.2f}")
        except:
            formatted.append(f"{roman}: {p:.2f}")
    return ", ".join(formatted)

# Returns (System Key, Root, Quality) given user input
# If user_input is None, asks for it interactively
def get_starting_chord(default_key: str, user_input: Optional[str] = None):
    if user_input is None:
        prompt = f"Enter Starting Chord (e.g. C, Am, G7, Bbmaj7) [default {default_key}]: "
        try:
            user_input = input(prompt)
            print()
        except EOFError:
            logger.info("[ERROR] Starting chord not recognized, using default C.")
            user_input = ""
    user_input = user_input.strip()

    if not user_input:
        return default_key, default_key, 'major' # System Key, Root, Quality
        
    # Parse input
    root, quality = parse_compact_chord(user_input)
    
    # Validate root is a valid note
    if normalize_note(root) not in NOTES:
        logger.warning(f"[WARNING] Invalid chord '{user_input}'. Using default {default_key}.")
        return default_key, default_key, 'major'
    
    # Key selection logic
    # 1. Minor Context -> Relative Major (Root + 3 semitones)
    if quality in MINOR_QUALITIES and quality not in DIMINISHED_QUALITIES:
        try:
            root_idx = NOTES.index(normalize_note(root))
            key_idx = (root_idx + 3) % 12
            system_key = NOTES[key_idx]
            logger.info(f"[INFO] Detected Minor context ({root}{quality}). Setting System Key to Relative Major: {system_key}")
        except ValueError:
            logger.warning(f"[WARNING] Could not determine key for {root}. Defaulting to C.")
            system_key = 'C'

    # 2. Diminished/Leading Tone Context -> Semitone Up Major (Root + 1 semitone)
    elif quality in DIMINISHED_QUALITIES:
        try:
            root_idx = NOTES.index(normalize_note(root))
            key_idx = (root_idx + 1) % 12
            system_key = NOTES[key_idx]
            logger.info(f"[INFO]Detected diminished context ({root}{quality}). Setting System Key to Resolution Major: {system_key}")
        except ValueError:
            logger.warning(f"[WARNING] Could not determine key for {root}. Defaulting to C.")
            system_key = 'C'

    # 3. Major/Dominant/Sus Context -> Root Major
    else:
        system_key = normalize_note(root)
        
    return system_key, root, quality
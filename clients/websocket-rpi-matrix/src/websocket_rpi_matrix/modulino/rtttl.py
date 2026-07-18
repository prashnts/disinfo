import re
from dataclasses import dataclass

@dataclass
class Note:
    note: str
    frequency: float
    duration: float

time_scale = 29.22
# time_scale = 1

NOTES: dict[str, int] = {
    "FS3": 185,
    "G3": 196,
    "GS3": 208,
    "A3": 220,
    "AS3": 233,
    "B3": 247,
    "C4": 262,
    "CS4": 277,
    "D4": 294,
    "DS4": 311,
    "E4": 330,
    "F4": 349,
    "FS4": 370,
    "G4": 392,
    "GS4": 415,
    "A4": 440,
    "AS4": 466,
    "B4": 494,
    "C5": 523,
    "CS5": 554,
    "D5": 587,
    "DS5": 622,
    "E5": 659,
    "F5": 698,
    "FS5": 740,
    "G5": 784,
    "GS5": 831,
    "A5": 880,
    "AS5": 932,
    "B5": 988,
    "C6": 1047,
    "CS6": 1109,
    "D6": 1175,
    "DS6": 1245,
    "E6": 1319,
    "F6": 1397,
    "FS6": 1480,
    "G6": 1568,
    "GS6": 1661,
    "A6": 1760,
    "AS6": 1865,
    "B6": 1976,
    "C7": 2093,
    "CS7": 2217,
    "D7": 2349,
    "DS7": 2489,
    "E7": 2637,
    "F7": 2794,
    "FS7": 2960,
    "G7": 3136,
    "GS7": 3322,
    "A7": 3520,
    "AS7": 3729,
    "B7": 3951,
    "C8": 4186,
    "CS8": 4435,
    "D8": 4699,
    "DS8": 4978,
    "REST": 0
}

def rtttl_to_notes(rtttl: str) -> list[Note]:
    # Parse RTTTL sections
    name_match = re.match(r'^([^:]+):', rtttl)
    defaults_match = re.search(r':([^:]+):', rtttl)
    data_match = re.search(r':([^:]+)$', rtttl)

    print(f"Parsing RTTTL: {rtttl}")

    if not all([name_match, defaults_match, data_match]):
        raise ValueError("Invalid RTTTL format")

    defaults = {}
    for part in defaults_match.group(1).split(','):
        if '=' in part:
            key, value = part.split('=')
            defaults[key] = int(value)

    default_duration = defaults.get('d', 4)
    default_octave = defaults.get('o', 5)
    bpm = defaults.get('b', 63)

    # Calculate timing
    seconds_per_beat = (60.0 / bpm) * 1
    base_frequencies = {
        'c': 261.63, 'c#': 277.18, 'd': 293.66, 'd#': 311.13,
        'e': 329.63, 'f': 349.23, 'f#': 369.99, 'g': 392.00,
        'g#': 415.30, 'a': 440.00, 'a#': 466.16, 'b': 493.88
    }

    notes = []
    data_string = data_match.group(1)

    for note_str in data_string.split(','):
        note_str = note_str.strip()
        if not note_str:
            continue

        duration_match = re.match(r'^(\d+)', note_str)
        if duration_match:
            duration = int(duration_match.group(1))
            note_str = note_str[duration_match.end():]
        else:
            duration = default_duration

        dotted = note_str.endswith('.')
        if dotted:
            note_str = note_str[:-1]

        note_match = re.match(r'^([a-g]#?|p)(\d*)$', note_str.lower())
        if not note_match:
            raise ValueError(f"Invalid note format: {note_str}")

        note = note_match.group(1)
        octave_str = note_match.group(2)

        if octave_str:
            octave = int(octave_str)
        else:
            octave = default_octave

        if note == 'p':
            frequency = 0.0
            note_name = 'REST'
        else:
            octave_offset = octave - 4
            base_freq = base_frequencies[note]
            frequency = base_freq * (2 ** octave_offset)
            note_name = note.upper() + str(octave)

        duration_seconds = duration * seconds_per_beat
        if dotted:
            duration_seconds *= 1.5

        notes.append(Note(note_name, frequency, duration_seconds))

        print(note_str, note_name, frequency, duration_seconds)

    return [(note.note.replace('#', 'S'), int(note.duration * time_scale)) for note in notes]



def notes_to_rtttl(notes: list[tuple], name: str = "Song", 
                   default_duration: int = 4, default_octave: int = 5, 
                   bpm: int = 63, _scale: float = 1) -> str:
    """Convert list of Note objects back to RTTTL format."""

    notes = [Note(note=note, frequency=NOTES[note], duration=duration / time_scale) for note, duration in notes]

    # Calculate timing
    seconds_per_beat = 60.0 / bpm
    base_frequencies = {
        'c': 261.63, 'c#': 277.18, 'd': 293.66, 'd#': 311.13,
        'e': 329.63, 'f': 349.23, 'f#': 369.99, 'g': 392.00,
        'g#': 415.30, 'a': 440.00, 'a#': 466.16, 'b': 493.88,
    }

    def frequency_to_note(frequency: float) -> tuple:
        """Convert frequency to (note, octave) tuple."""
        if frequency == 0.0:
            return ('p', None)

        # Find closest note
        best_note = None
        best_octave = None
        min_diff = float('inf')

        for octave in range(4, 8):  # RTTTL standard octaves
            for note, base_freq in base_frequencies.items():
                freq = base_freq * (2 ** (octave - 4))
                diff = abs(frequency - freq)
                if diff < min_diff:
                    min_diff = diff
                    best_note = note
                    best_octave = octave

        return (best_note, best_octave)

    def duration_to_rtttl(duration: float, dotted: bool = False) -> str:
        """Convert duration in seconds to RTTTL duration code."""
        # Try common durations
        duration = duration / _scale
        duration_codes = [1, 2, 4, 8, 16, 32]
        duration = duration / (1.5 if dotted else 1.0)

        def get_code(duration: float):
            beats = duration / seconds_per_beat

            # Find closest duration code
            best_code = None
            min_diff = float('inf')

            for code in duration_codes:
                diff = abs(code - beats)
                if diff < min_diff:
                    min_diff = diff
                    best_code = code

            # return str(int(beats))
            return str(best_code)
        
        return get_code(duration)

    # Build RTTTL string
    note_strings = []

    for note in notes:
        # Determine note and octave
        note_name, octave = frequency_to_note(note.frequency)

        # Handle pauses
        if note_name == 'p':
            if note.duration == default_duration * seconds_per_beat:
                note_str = 'p'
            else:
                duration_str = duration_to_rtttl(note.duration)
                note_str = f"{duration_str}p"
        else:
            # Determine if we need to specify duration
            uses_default_duration = abs(note.duration - default_duration * seconds_per_beat) < 0.001

            # Determine if we need to specify octave
            uses_default_octave = octave == default_octave

            # Check if dotted
            duration_without_dot = note.duration / 1.5
            is_dotted = abs(duration_without_dot * seconds_per_beat - round(duration_without_dot / seconds_per_beat)) < 0.001

            if is_dotted:
                actual_duration = duration_without_dot
            else:
                actual_duration = note.duration

            duration_str = '' if uses_default_duration else duration_to_rtttl(actual_duration, is_dotted)

            # Build note string
            note_str = note_name
            if not uses_default_octave:
                note_str += str(octave)

            if duration_str:
                note_str = duration_str + note_str

            if is_dotted:
                note_str += '.'

        note_strings.append(note_str)

    # Complete RTTTL string
    defaults = f"d={default_duration},o={default_octave},b={bpm}"
    data = ','.join(note_strings)

    return f"{name}:{defaults}:{data}"


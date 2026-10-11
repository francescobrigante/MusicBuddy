# ==================================================================================================================
# MusicBuddy entry point
#
# Starts the real-time accompaniment pipeline. Defaults come from src/config.py and can be
# overridden from the command line (run `python main.py --help`).
# ==================================================================================================================

import argparse
import os
import sys

import mido

from src.config import (
    OUTPUT_PORT, INPUT_PORT, WINDOW_SIZE, DEFAULT_SOUNDFONT, MODEL_PATH, VOCAB_PATH,
    DEFAULT_BPM, DEFAULT_BEATS_PER_BAR, DEFAULT_KEY, SESSION_MAX_CHORDS
)
from src.utils.logger import setup_logger
from src.utils.music_theory import get_starting_chord

logger = setup_logger()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MusicBuddy: a real-time AI accompanist for your MIDI instrument.")
    parser.add_argument("--list-ports", action="store_true", help="list the available MIDI ports and exit")
    parser.add_argument("--input-port", default=INPUT_PORT, help=f"MIDI port you play into (default: '{INPUT_PORT}')")
    parser.add_argument("--output-port", default=OUTPUT_PORT, help=f"MIDI port the accompaniment is sent to (default: '{OUTPUT_PORT}')")
    parser.add_argument("--start-chord", help="starting chord, e.g. C, Am, G7, Bbmaj7 (asked interactively if omitted)")
    parser.add_argument("--bpm", type=float, default=DEFAULT_BPM, help=f"tempo, or starting tempo with dynamic BPM (default: {DEFAULT_BPM})")
    bpm_mode = parser.add_mutually_exclusive_group()
    bpm_mode.add_argument("--dynamic-bpm", dest="dynamic_bpm", action="store_true", default=None, help="follow your tempo in real time")
    bpm_mode.add_argument("--static-bpm", dest="dynamic_bpm", action="store_false", help="keep the tempo fixed at --bpm")
    parser.add_argument("--soundfont", default=DEFAULT_SOUNDFONT, help=f"SoundFont (.sf2) for playback and metronome (default: {DEFAULT_SOUNDFONT})")
    parser.add_argument("--no-metronome", action="store_true", help="disable the metronome click")
    return parser.parse_args()


def list_ports():
    print("MIDI input ports (use with --input-port):")
    for name in mido.get_input_names():
        print(f"  {name}")
    print("MIDI output ports (use with --output-port):")
    for name in mido.get_output_names():
        print(f"  {name}")


# Opens and closes each port once, so a wrong name fails here instead of mid-session
def check_ports(input_port: str, output_port: str) -> bool:
    checks = [(input_port, mido.open_input, "input"), (output_port, mido.open_output, "output"),
              (output_port, mido.open_input, "input (synth loopback)")]
    ok = True
    for name, opener, role in checks:
        try:
            opener(name).close()
        except OSError as e:
            logger.error(f"[MIDI] Cannot open '{name}' as {role}: {e}")
            ok = False
    if not ok:
        logger.error("[MIDI] Run `python main.py --list-ports` and see docs/midi_setup.md")
    return ok


# Checks the files the session needs before opening any device
def check_files(soundfont: str) -> bool:
    missing = [p for p in (MODEL_PATH, VOCAB_PATH) if not os.path.exists(p)]
    for path in missing:
        logger.error(f"[MODEL] Missing {path}. Train the model first: see docs/training.md")
    if not os.path.exists(soundfont):
        logger.warning(f"[SYNTH] SoundFont not found at {soundfont}: no audio from the built-in synth (see docs/midi_setup.md)")
    return not missing


def ask_dynamic_bpm() -> bool:
    try:
        return input("Use dynamic BPM detection? [Y/n]: ").strip().lower() != 'n'
    except EOFError:
        return True


def main() -> int:
    args = parse_args()

    if args.list_ports:
        list_ports()
        return 0

    logger.info("=" * 50)
    logger.info("MUSICBUDDY: REAL-TIME ACCOMPANIMENT")
    logger.info("=" * 50)

    if not check_files(args.soundfont) or not check_ports(args.input_port, args.output_port):
        return 1

    # Imported here so that --help and --list-ports do not load torch and FluidSynth
    from src.pipeline import RealTimePipeline

    system_key, start_root, start_quality = get_starting_chord(DEFAULT_KEY, args.start_chord)
    use_dynamic_bpm = args.dynamic_bpm if args.dynamic_bpm is not None else ask_dynamic_bpm()

    bpm_mode_str = "Dynamic" if use_dynamic_bpm else f"Static ({args.bpm:g})"
    print()
    logger.info(f"Starting System: Key = {system_key} | Starting Chord = {start_root}{start_quality} | BPM: {bpm_mode_str}")

    try:
        pipeline = RealTimePipeline(
            key=system_key,                             # Musical key (for AI context)
            starting_root=start_root,                   # Actual starting chord root
            starting_quality=start_quality,             # Actual starting chord quality
            bpm=args.bpm,                               # Tempo in BPM
            beats_per_bar=DEFAULT_BEATS_PER_BAR,        # How many beats in one bar
            window_size=WINDOW_SIZE,                    # How many chords to consider for prediction
            max_sequence_length=SESSION_MAX_CHORDS,     # Maximum generated sequence length in chords
            output_port=args.output_port,               # Output port for MIDI playback (listen)
            input_port=args.input_port,                 # Input port for MIDI input (play)
            enable_input_listener=True,                 # Enable MIDI input listener
            enable_metronome=not args.no_metronome,     # Enable metronome
            enable_synth=True,                          # Enable MIDI synth
            enable_dynamic_bpm=use_dynamic_bpm,         # Enable dynamic BPM detection
            soundfont_path=args.soundfont               # SoundFont for synth and metronome
        )

        # Start pipeline
        final_sequence = pipeline.start()

        # Show results
        logger.info("=" * 50)
        logger.info("FINAL SEQUENCE:")
        logger.info("=" * 50)

        sequence_names = pipeline.get_current_sequence()
        for i, (chord_obj, chord_name) in enumerate(zip(final_sequence, sequence_names)):
            logger.info(f"Chord {i+1}: {chord_name} ({chord_obj.root} {chord_obj.chord_type})")

        logger.info(f"Total duration: {len(final_sequence) * pipeline.chord_duration_seconds:.1f} seconds")

    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

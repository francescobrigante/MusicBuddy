# MIDI and audio setup

MusicBuddy talks to the outside world through two MIDI ports and makes sound with FluidSynth.

## How the ports are used

```
 your instrument ──► INPUT PORT ──► MusicBuddy ──► OUTPUT PORT ──┐
 (keyboard / VMPK)   --input-port   (Ear, BPM)    --output-port  │  loopback
                                                                 ▼
                                          MusicBuddy's built-in FluidSynth
                                          plays your notes + the chords
```

- **Input port** (`--input-port`, default `IAC Piano OUT`): where MusicBuddy listens to what you
  play. Your notes feed the Ear (harmony) and the BPM detector, and are also played by the
  built-in synth.
- **Output port** (`--output-port`, default `IAC Piano IN`): where MusicBuddy sends the
  accompaniment chords. MusicBuddy also *listens* to this port to play the chords through its
  synth, so it must be a **loopback** port, readable and writable (a virtual MIDI bus). A virtual
  keyboard connected to it shows the chords as they are played.

List the port names that MusicBuddy sees:

```bash
uv run python main.py --list-ports
```

and pass them on the command line, e.g.
`uv run python main.py --input-port "Digital Piano" --output-port "IAC Driver Bus 1"`.
To change the defaults permanently, edit `INPUT_PORT` and `OUTPUT_PORT` in `src/config.py`.

## 1. FluidSynth

Install the FluidSynth library (the `pyfluidsynth` Python package only wraps it):

| OS | Command |
|---|---|
| macOS | `brew install fluidsynth` |
| Debian / Ubuntu | `sudo apt-get install fluidsynth` |
| Windows | `choco install fluidsynth` (make sure its `bin` folder is on `PATH`) |

## 2. SoundFont

FluidSynth needs a SoundFont (`.sf2`) with the instrument sounds. MusicBuddy is set up for
[GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS) (about 32 MB; see its license):

```bash
mkdir -p data
curl -L -o data/GeneralUser-GS.sf2 \
  https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2
```

Any General MIDI SoundFont works: put it anywhere and pass `--soundfont path/to/file.sf2`.
The chord instrument is `DEFAULT_PROGRAM` in `src/config.py` (a General MIDI program number;
`src/soundfonts.py` lists the names).

Without a SoundFont MusicBuddy still runs and sends the chords to the output port, but its
built-in synth and the metronome are silent.

## 3. Virtual MIDI ports

### macOS (tested)

1. Open **Audio MIDI Setup** (`/Applications/Utilities/Audio MIDI Setup.app`).
2. **Window → Show MIDI Studio**, double-click **IAC Driver**, tick **Device is online**.
3. Add two ports named `IAC Piano IN` and `IAC Piano OUT`, which are MusicBuddy's defaults.
   With other names, pass them with `--input-port` / `--output-port`.

### Windows (not tested)

Windows has no built-in virtual MIDI ports. Install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html)
and create two ports, e.g. `MusicBuddy In` and `MusicBuddy Out`; then pass them with
`--input-port` / `--output-port`.

### Linux (not tested)

Load the ALSA virtual MIDI driver, which creates loopback ports:

```bash
sudo modprobe snd-virmidi
uv run python main.py --list-ports    # look for "Virtual Raw MIDI" ports
```

Use one of them as the output port; connect your instrument (or VMPK) to the input port with
`aconnect` or a patchbay such as `qjackctl`.

## 4. Choose your instrument

### Physical MIDI keyboard

Connect it over USB and pass its port name as the input:

```bash
uv run python main.py --input-port "Digital Piano"
```

The output port is still a virtual loopback port (`IAC Piano IN` by default on macOS).

### No keyboard: VMPK

[VMPK](https://vmpk.sourceforge.io/) is a free virtual piano keyboard. In its MIDI connections:

- **MIDI OUT** → `IAC Piano OUT` (MusicBuddy's input port): what you play;
- **MIDI IN** ← `IAC Piano IN` (MusicBuddy's output port): VMPK lights up the chords it plays.

## Troubleshooting

- **`Cannot open '...' as input/output`**: the port name does not match exactly. Copy it from
  `--list-ports`; on macOS make sure the IAC Driver is online.
- **`[SYNTH] Failed to initialize FluidSynth`**: the FluidSynth library is not installed or not
  found (step 1), or the SoundFont path is wrong (step 2).
- **No chords, `No notes played, waiting...`**: MusicBuddy waits for you, and plays a new chord
  only after a bar in which you played something. Check that your instrument sends to the input port.
- **Double sound**: if your keyboard has its own speakers, MusicBuddy's synth plays your notes as
  well; turn one of the two down.

<h1 align="center">MusicBuddy</h1>

<p align="center"><b>A real-time AI accompanist that listens to your MIDI instrument, understands your harmony, and plays chords with you.</b></p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=rMqet5fySLI"><img src="https://img.shields.io/badge/Live%20demo-YouTube-red?logo=youtube&logoColor=white" alt="Live demo on YouTube"></a>
  <a href="https://drive.google.com/drive/folders/1KKQupkoti1squj6vKVpUubwYWhwCmCqf?usp=drive_link"><img src="https://img.shields.io/badge/Listen-examples-4285F4?logo=google-drive&logoColor=white" alt="Audio examples"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
</p>

<p align="center">
  <img src="resources/realtime_example.gif" width="700" alt="Real-time chord accompaniment generated while a soloist plays">
</p>

You play a melody on a MIDI keyboard (or a virtual one); MusicBuddy follows your key and tempo
and answers, bar by bar, with the chord that fits. It is a hybrid of a **deep-learning model**,
which knows how songs usually move, and a **rule-based music-theory module**, which listens to
what you are playing right now.

**What do you want to do?**

- Play with MusicBuddy → [Quickstart](#quickstart)
- Connect your keyboard, or play without one → [MIDI and audio setup](docs/midi_setup.md)
- Train the chord model → [Training guide](docs/training.md)

## Quickstart

**1. Install.** You need Python 3.11, [uv](https://docs.astral.sh/uv/) and the FluidSynth library.

```bash
brew install fluidsynth          # macOS; Linux and Windows: see docs/midi_setup.md
git clone https://github.com/francescobrigante/MusicBuddy.git
cd MusicBuddy
uv sync
```

**2. Get a SoundFont** for the instrument sounds (GeneralUser GS, about 32 MB):

```bash
mkdir -p data
curl -L -o data/GeneralUser-GS.sf2 https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2
```

**3. Train the chord model.** Pretrained weights are coming soon; until then, follow the
[training guide](docs/training.md). It produces `data/best_model.pth` and `data/vocab.pkl`.

**4. Set up two MIDI ports** (on macOS, two IAC Driver ports named `IAC Piano IN` and
`IAC Piano OUT`) as described in [MIDI and audio setup](docs/midi_setup.md), and check that
MusicBuddy sees them:

```bash
uv run python main.py --list-ports
```

**5. Play.**

```bash
uv run python main.py
```

MusicBuddy asks for a starting chord and whether to follow your tempo, counts one bar of
metronome, and starts. It plays a new chord every bar in which you played something; stop
with `Ctrl+C`.

## Command-line options

Every option has a default in [`src/config.py`](src/config.py).

| Option | Default | Description |
|---|---|---|
| `--list-ports` | | list the MIDI ports and exit |
| `--input-port NAME` | `IAC Piano OUT` | the port you play into (your keyboard, or VMPK) |
| `--output-port NAME` | `IAC Piano IN` | the loopback port the chords are sent to |
| `--start-chord CHORD` | asked | starting chord, e.g. `C`, `Am`, `G7`, `Bbmaj7`; it also sets the starting key |
| `--dynamic-bpm` / `--static-bpm` | asked | follow your tempo, or keep it fixed |
| `--bpm N` | `120` | the tempo, or the starting tempo with `--dynamic-bpm` |
| `--soundfont PATH` | `data/GeneralUser-GS.sf2` | SoundFont for the synth and the metronome |
| `--no-metronome` | | no click track |

For example, a session with a physical keyboard, starting in A minor at a fixed 90 BPM:

```bash
uv run python main.py --input-port "Digital Piano" --start-chord Am --static-bpm --bpm 90
```

Other settings (sampling, the weight of the model against the Ear, the instrument, the metronome
sound) are constants in `src/config.py`.

## How it works

### The hybrid engine

Each chord is the result of two predictions, made with different time horizons:

**Macro-prediction: the Brain.** An LSTM trained on the chord progressions of the
[Chordonomicon](https://huggingface.co/datasets/ailsntua/Chordonomicon) dataset predicts the next
chord, as a Roman numeral, from the last 8 chords played. It works ahead of time: a background
thread precomputes the next 10 chords, and recomputes them whenever the actual chord differs from
the predicted one, so the model never sits on the critical path.

**Micro-correction: the Ear.** A deterministic, low-latency module analyses the notes you
played during the current bar:

- **Key detection:** the Krumhansl-Schmuckler algorithm finds the key you are playing in, and
  MusicBuddy moves to the new key when you modulate.
- **Harmonic function:** your notes are weighted (recent notes count more) and mapped to the
  tonic, subdominant or dominant function, which gives a distribution over the possible next chords.
- **Fusion:** the two distributions are merged by a weighted sum, and the most likely chord is played.

### Real-time engineering

Several threads, synchronized by a central clock, the **Conductor**:

| Thread | Role |
|---|---|
| **Timing** | the heartbeat: at every bar line it asks the Predictor for the chord and schedules it |
| **Playback** | sends the chords to the output port, decoupled from the prediction logic |
| **Listener** | captures your MIDI input asynchronously, for the Ear and the BPM detector |
| **Metronome** | click track aligned to the Conductor |
| **Predictor** | background LSTM precomputation (thread pool), non-blocking |

Every thread reads the current tempo and bar timing from the Conductor, so they stay aligned
when the tempo changes.

### Dynamic tempo

With `--dynamic-bpm`, MusicBuddy follows your tempo. It estimates the BPM from the
inter-onset intervals (IOI) of your notes over a sliding window, ignores small fluctuations
(hysteresis), and confirms a tempo jump only after several consecutive notes agree on it.

## Latency

Every session writes per-chord timings to `logs/`; `tools/analyze_latency.py` summarizes them.
On the example session in [`docs/latency_example.json`](docs/latency_example.json) (119 chords):

| Metric | Mean | Std | Max |
|---|---|---|---|
| Processing latency: time to choose the chord (precomputed LSTM prediction, key detection, Ear, fusion) | 3.1 ms | 0.9 ms | 6.7 ms |
| Alignment jitter: delay between the bar line and the chord being scheduled (thread wake-up + processing) | 5.5 ms | 1.7 ms | 10.2 ms |

```bash
uv run python tools/analyze_latency.py docs/latency_example.json   # or no argument: the latest session in logs/
```

## Limitations

- Major keys only: minor passages are read in their relative major key.
- One chord per bar, in 4/4.
- The accompaniment is block chords played by one instrument.
- Pretrained weights are not released yet (see [Quickstart](#quickstart), step 3).

## Roadmap

- Release pretrained weights.
- More accurate BPM detection.
- More robust and more creative accompaniment.

## Repository layout

```
main.py                   entry point: command-line options, port checks, session start
data_processing.py        Chordonomicon → Roman-numeral dataset (training step 1)
src/
  config.py               all settings: ports, paths, model, timing, sampling, music theory
  soundfonts.py           General MIDI program numbers by instrument name
  audio/                  MIDI and audio I/O: Conductor clock, metronome, MIDI listener, FluidSynth
  music/                  Ear, key detector, BPM detector, Chord object
  model/                  LSTM, vocabulary, inference wrapper (ai_harmony.py)
    train/                dataloader and training loop
  pipeline/               real-time orchestration: timing thread, predictor (LSTM + Ear), playback
  utils/                  logger, music-theory helpers (Roman numerals, chord parsing)
tools/analyze_latency.py  latency report of a session
docs/                     training guide, MIDI setup, example latency log
```

## Acknowledgements

- [Chordonomicon](https://huggingface.co/datasets/ailsntua/Chordonomicon) (CC BY-NC 4.0), the
  chord-progression dataset the model is trained on.
- [FluidSynth](https://www.fluidsynth.org/) and [pyFluidSynth](https://github.com/nwhitehead/pyfluidsynth)
  for sound, [mido](https://github.com/mido/mido) and [python-rtmidi](https://github.com/SpotlightKid/python-rtmidi)
  for MIDI, [PyTorch](https://pytorch.org/) for the model.
- [GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS) by S. Christian Collins, the
  default SoundFont (not included in this repository).
- The key detector follows the Krumhansl-Schmuckler key-finding algorithm (C. L. Krumhansl,
  *Cognitive Foundations of Musical Pitch*, 1990).

## License

The code is released under the [MIT License](LICENSE). Models trained on Chordonomicon are subject
to its non-commercial license (CC BY-NC 4.0).

## Citation

If you use MusicBuddy, please cite this repository:

```bibtex
@software{brigante2025musicbuddy,
  author = {Brigante, Francesco},
  title  = {{MusicBuddy}: A Real-Time {AI} Accompanist},
  year   = {2025},
  url    = {https://github.com/francescobrigante/MusicBuddy}
}
```

and the Chordonomicon dataset:

```bibtex
@article{kantarelis2024chordonomicon,
  title={CHORDONOMICON: A Dataset of 666,000 Songs and their Chord Progressions},
  author={Kantarelis, Spyridon and Thomas, Konstantinos and Lyberatos, Vassilis and Dervakos, Edmund and Stamou, Giorgos},
  journal={arXiv preprint arXiv:2410.22046},
  year={2024}
}
```

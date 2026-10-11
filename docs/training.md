# Training the chord model

MusicBuddy's "Brain" is an LSTM that predicts the next chord, as a Roman numeral, from the last
8 chords. Pretrained weights are not released yet, so you need to train your own before the first
session. A full run fits on a laptop: the model has about 6M parameters and trains on CUDA, Apple
Silicon (MPS) or CPU.

The pipeline has three steps; each one reads the output of the previous one from `data/`:

```
data/chordonomicon_v2.csv ──► data_processing.py ──► data/clean_dataset.pkl
                                                         │
                                 src/model/vocabulary.py ┴─► data/vocab.pkl
                                                         │
                              src/model/train/train.py ──┴─► data/best_model.pth
```

All paths and hyperparameters live in [`src/config.py`](../src/config.py).

## 1. Install the training extras

```bash
uv sync --extra train
```

This adds `pandas`, `tqdm` and `matplotlib` to the real-time dependencies.

## 2. Download the dataset

MusicBuddy is trained on [Chordonomicon](https://huggingface.co/datasets/ailsntua/Chordonomicon),
the chord progressions of about 666k songs. Download `chordonomicon_v2.csv` (about 264 MB) into
`data/`:

```bash
mkdir -p data
curl -L -o data/chordonomicon_v2.csv \
  https://huggingface.co/datasets/ailsntua/Chordonomicon/resolve/main/chordonomicon_v2.csv
```

Chordonomicon is released under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/):
a model trained on it is for non-commercial use.

## 3. Preprocess: chords to Roman numerals

```bash
uv run python data_processing.py
```

For every song, in parallel on all CPU cores, the script:

1. cleans the chord tokens: drops the section tags (`<verse_1>`, ...) and slash-chord basses, and
   maps the dataset's `s` to `#` (`Fs7` → `F#7`) and `min` to `m`;
2. detects the song's major key with the Krumhansl-Schmuckler key detector
   (`src/music/key_detector_major.py`), the same one used live;
3. **drops songs whose key confidence is below 0.79**, so that the Roman numerals are reliable;
4. converts each chord to a Roman numeral relative to the key (`C F G7` in C → `I IV V7`).

Outputs:

- `data/clean_dataset.pkl`: the list of songs as Roman-numeral sequences, the training input;
- `data/clean_dataset.csv`: one row per song (key, confidence, numerals, original chords) for
  inspection.

Songs where no key can be detected are logged as `[FAILED]`; it is normal to see some.

## 4. Build the vocabulary

```bash
uv run python -m src.model.vocabulary
```

This maps each Roman numeral to an index (`0` = `<PAD>`, `1` = `<UNK>`), saves `data/vocab.pkl` and
runs a round-trip check (chord → numeral → index → numeral → chord) on a few test chords. A `PART`
status there only means an enharmonic spelling (`Bbadd9` comes back as `A#add9`).

## 5. Train

```bash
uv run python -m src.model.train.train
```

The script builds every window of 8 chords and the chord that follows (the start of each song is
left-padded, so the model also learns to predict from a short history), splits the windows 80/20
into train and validation, and trains with:

| Setting | Value (`src/config.py`) |
|---|---|
| Window | `WINDOW_SIZE = 8` chords |
| Model | embedding 256 → 3-layer LSTM, hidden 512, dropout 0.3 → linear over the vocabulary |
| Loss | cross-entropy, label smoothing 0.1 |
| Optimizer | AdamW, lr `2e-4`, weight decay `1e-4`, OneCycle schedule, gradient clipping at 1.0 |
| Batch / epochs | 1024 / 8 |
| Precision | mixed precision on CUDA, fp32 on MPS and CPU |

After each epoch it logs train and validation loss and accuracy, saves the best checkpoint (by
validation accuracy) to `data/best_model.pth`, and updates `data/training_plot.png` and
`data/training_plot_history.pkl`.

<!-- TODO(Francesco): reference numbers of a full run, e.g.
| Hardware | Time per epoch | Best val accuracy |
|---|---|---|
| ... | ... | ... |
-->

> **Changing the architecture.** `HIDDEN_SIZE`, `EMBEDDING_DIM`, `NUM_LAYERS` and `WINDOW_SIZE` are
> read both at training time and when the live session loads the model. If you change them, train
> again: an old checkpoint fails to load with a shape-mismatch error. Rebuild the vocabulary
> (step 4) whenever you change the preprocessing.

## Sampling settings for live play

These do not affect training; they control how the trained model is used during a session:

| Setting | Default | Effect |
|---|---|---|
| `SAMPLING_TEMPERATURE` | 0.13 | lower = more predictable progressions |
| `SAMPLING_TOP_K` | 85 | sample only among the k most likely chords |
| `USE_DETERMINISTIC_SAMPLING` | `False` | `True` always takes the most likely chord |
| `AI_WEIGHT` | 0.1 | weight of the LSTM against the Ear when merging their predictions (1.0 = LSTM only) |
| `CHORDS_TO_PRECOMPUTE` | 10 | chords the LSTM predicts ahead in the background |

Temperature and top-k were chosen with an Optuna hyperparameter search (the search script is not
part of this repository).

## Check the result

Once `data/best_model.pth` and `data/vocab.pkl` exist, start a session (see the
[README](../README.md#quickstart)):

```bash
uv run python main.py
```

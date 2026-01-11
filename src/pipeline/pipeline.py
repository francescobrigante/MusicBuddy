# ==================================================================================================================
# Real-Time Accompaniment Pipeline
# ==================================================================================================================
# Orchestrates the real-time accompaniment pipeline
# Contains timing thread which is the main thread for prediction and timing alignment
# Uses Conductor for dynamic BPM and timing
# Contains start() function: main entry point for the pipeline
# ==================================================================================================================

import time
import threading
import json
import datetime
import os
from pathlib import Path
from typing import List, Optional

from src.config import (
    OUTPUT_PORT, DELAY_START_SECONDS, EMPTY_BARS_COUNT,
    DEFAULT_BPM, DEFAULT_BEATS_PER_BAR, WINDOW_SIZE, 
    DEFAULT_MAX_SEQUENCE_LENGTH, CHORDS_TO_PRECOMPUTE
)
from src.utils.logger import setup_logger
from src.utils.music_theory import compact_chord, chord_to_roman
from src.music.chord import Chord

from src.pipeline.predictor import Predictor
from src.pipeline.playback import PlaybackThread
from src.audio.metronome import Metronome
from src.audio.midi_listener import MIDIListener
from src.audio.midi_listener import create_playback_synth
from src.audio.clock import Conductor
from src.music.bpm_detector import BPMDetector

logger = setup_logger()

class RealTimePipeline:
    
    def __init__(self, key: str = 'C', starting_root: Optional[str] = None, starting_quality: str = 'major', 
                 bpm: int = DEFAULT_BPM, beats_per_bar: float = DEFAULT_BEATS_PER_BAR, window_size: int = WINDOW_SIZE, 
                 max_sequence_length: int = DEFAULT_MAX_SEQUENCE_LENGTH, output_port: str = OUTPUT_PORT, 
                 input_port: Optional[str] = None, enable_input_listener: bool = False, 
                 enable_metronome: bool = True, empty_bars_count: int = EMPTY_BARS_COUNT,
                 enable_synth: bool = True, enable_dynamic_bpm: bool = True):
        
        # Configuration
        self.key = key
        self.bpm = bpm
        self.beats_per_bar = beats_per_bar
        self.window_size = window_size
        self.max_sequence_length = max_sequence_length
        self.output_port = output_port
        self.input_port = input_port
        self.enable_input_listener = enable_input_listener
        self.enable_metronome = enable_metronome
        self.enable_dynamic_bpm = enable_dynamic_bpm
        self.empty_bars_count = empty_bars_count
        self.enable_synth = enable_synth
        
        # Performance Metrics: stores values for latency analysis
        self.perf_metrics = []

        # Conductor
        self.conductor = Conductor(
            initial_bpm=bpm, 
            beats_per_bar=beats_per_bar,
            on_tempo_change=self._on_tempo_change
        )
        
        # BPM Detector (Dynamic Timing)
        if self.enable_dynamic_bpm:
            self.bpm_detector = BPMDetector(conductor=self.conductor)
        else:
            self.bpm_detector = None
        
        # Predictor (Predicts the next chord)
        self.predictor = Predictor(key, bpm, beats_per_bar, window_size)
            
        # FluidSynth (for Playback)
        self.synth = None
        self.synth_listener = None
        if self.enable_synth and self.output_port:
            try:
                # Synth listener monitors the output port (loopback)
                self.synth, self.synth_listener = create_playback_synth(midi_port_name=self.output_port)
                logger.info(f"[SYNTH] FluidSynth initialized on {self.output_port}")
            except Exception as e:
                logger.error(f"[SYNTH] Failed to initialize FluidSynth: {e}")

        # MIDI Input Listener (for Ear and BPM)
        if self.enable_input_listener and self.input_port:
            self.midi_listener = MIDIListener(
                port_name=self.input_port, 
                synth_player=self.synth,
                bpm_detector=self.bpm_detector
            )
        else:
            self.midi_listener = None
        
        # Metronome (receives conductor)
        self.metronome = Metronome(
            self.bpm, 
            self.beats_per_bar, 
            self.empty_bars_count,
            conductor=self.conductor
        )
        
        self.metronome_thread = None
        self.timing_thread = None
        self.playback = None
        
        # State
        self.chord_objects = []                     # Shared list containing the chords to play
        self.current_chord_idx = 0                  # Current chord index
        self.is_running = False                     # Pipeline running flag
        self.start_time = None                      # Pipeline start time
        
        # Starting Chord
        root = starting_root if starting_root else key
        self.starting_chord = Chord(root, starting_quality, bpm, beats_per_bar)

    @property
    def chord_duration_seconds(self) -> float:
        """Get current chord duration in seconds (based on current BPM)."""
        if self.conductor:
            return self.conductor.bar_duration
        # Fallback
        return (self.beats_per_bar * 60.0) / self.bpm

    def _on_tempo_change(self, old_bpm, new_bpm):
        """Callback for Conductor tempo changes."""
        elapsed_s = time.time() - self.start_time if self.start_time else 0
        logger.info(f"[{elapsed_s:.1f}s] [BPM] Update: {old_bpm:.1f} -> {new_bpm:.1f} BPM")
        self.bpm = new_bpm
        
        # Update predictor so future chords have correct duration
        self.predictor.set_bpm(new_bpm)



    # MAIN THREAD: handles all chord scheduling, prediction and timing alignment
    def _timing_thread(self):
        
        # Get starting chord roman
        start_roman = chord_to_roman(self.key, self.starting_chord.root, self.starting_chord.chord_type)
        
        # Seed window
        self.predictor.chord_window.append(start_roman)
        self.predictor.precomputed_sequence = self.predictor.ai.precompute_sequence(list(self.predictor.chord_window), CHORDS_TO_PRECOMPUTE)
        self.predictor.precomputed_idx = 0

        # Start Conductor (sets t0)
        self.conductor.start()
        self.start_time = self.conductor.start_time
        
        # Delay (in bars) before first chord
        start_delay_seconds = self.empty_bars_count * self.conductor.bar_duration
        
        # Wait for start delay
        first_chord_time = self.start_time + start_delay_seconds
        while self.is_running:
            if time.time() >= first_chord_time:  # Exact timing
                break
            time.sleep(0.01)

        # Play starting chord
        self.chord_objects.append(self.starting_chord)
        
        # Initialize incremental timing: track when the last chord was scheduled
        last_chord_time = first_chord_time
        
        # Then set the current chord index to 1
        self.current_chord_idx = 1
        elapsed_s = time.time() - self.start_time if self.start_time else 0
        logger.info(f"[{elapsed_s:.1f}s] [🎶PLAYING STEP 1🎶] {self.starting_chord} (BPM: {self.bpm:.1f})")
        
        while self.is_running and self.current_chord_idx < self.max_sequence_length:
            # INCREMENTAL TIMING: Next chord is one bar after the last chord
            target_time = last_chord_time + self.conductor.bar_duration
            
            # Wait until target time (notes are collected during this period)
            while self.is_running:
                wait_time = target_time - time.time()
                if wait_time <= 0:
                    break
                time.sleep(min(wait_time, 0.05))
                
            if not self.is_running: break


            # Latency Measurement Start: before prediction
            t_start_processing = time.time()
            
            # Prediction (after notes collected)
            candidate_chord = self.predictor.get_next_prediction()
            
            if not candidate_chord:
                logger.warning("No prediction available, ending sequence.")
                break
                
            final_chord = self.predictor.refine_prediction(candidate_chord, self.midi_listener)
            
            # WAITING LOGIC: if no notes played, wait for input
            if not final_chord:
                elapsed_s = time.time() - self.start_time if self.start_time else 0
                logger.info(f"[{elapsed_s:.1f}s] [SYSTEM] No notes played, waiting...")
                last_chord_time = target_time
                self.current_chord_idx += 1
                if self.midi_listener: self.midi_listener.clear_note_window()
                continue
                
            # Schedule final chord
            self.chord_objects.append(final_chord)
            
            # Latency Measurement End: after chord is scheduled (for playing)
            t_end_processing = time.time()

            # Store metrics
            self.perf_metrics.append({
                'chord_idx': self.current_chord_idx + 1,
                'target_time': target_time,
                'start_processing': t_start_processing,
                'end_processing': t_end_processing,
                'processing_latency': t_end_processing - t_start_processing,
                'alignment_jitter': t_end_processing - target_time,
                'outcome': 'played'
            })
            
            last_chord_time = target_time
            
            # Sync key with predictor
            if self.key != self.predictor.key:
                self.key = self.predictor.key
            
            # Update History
            final_roman = chord_to_roman(self.key, final_chord.root, final_chord.chord_type)
            self.predictor.update_history(final_roman)
            
            self.current_chord_idx += 1
            elapsed_s = target_time - self.start_time if self.start_time else 0
            logger.info(f"[{elapsed_s:.1f}s] [🎶PLAYING STEP {self.current_chord_idx}🎶] {final_chord}")
            
            if self.midi_listener: self.midi_listener.clear_note_window()
            
        logger.info("[SYSTEM] Sequence complete!")
        self.is_running = False

    # REAL-TIME PIPELINE ENTRY POINT: Orchestrates all the threads
    def start(self):
        if self.is_running: return
        
        print()
        logger.info(f"[SYSTEM] Starting pipeline in {self.key} @ {self.bpm} BPM")
        self.is_running = True
        
        # Start Listeners
        if self.midi_listener: self.midi_listener.start()
        if self.synth_listener: self.synth_listener.start()
        
        # Threads
        threads = []
        
        # 1. Metronome
        if self.enable_metronome:
            self.metronome_thread = threading.Thread(
                target=self.metronome.run,
                # For static metronome fallback (unused if conductor present, but required by signature)
                args=(lambda: self.start_time, lambda: self.is_running, self.max_sequence_length),
                daemon=True,
            )
            self.metronome_thread.start()
            threads.append(self.metronome_thread)
            
        # 2. Timing (Predictor)
        self.timing_thread = threading.Thread(target=self._timing_thread, daemon=True)
        self.timing_thread.start()
        threads.append(self.timing_thread)
        
        # 3. Playback (Synth for output)
        start_beat_offset = self.empty_bars_count * self.beats_per_bar
        self.playback = PlaybackThread(
            chord_objects=self.chord_objects,
            output_port=self.output_port,
            max_sequence_length=self.max_sequence_length,
            is_running_func=lambda: self.is_running,
            conductor=self.conductor,
            start_beat_offset=start_beat_offset,
            beats_per_bar=self.beats_per_bar
        )
        self.playback.start()
        threads.append(self.playback)
        
        # Wait for threads to finish
        try:
            while True:
                threads_alive = False
                if self.timing_thread and self.timing_thread.is_alive():
                    self.timing_thread.join(timeout=0.1)
                    threads_alive = True
                if self.playback and self.playback.is_alive():
                    self.playback.join(timeout=0.1)
                    threads_alive = True
                
                if not threads_alive:
                    break

        except KeyboardInterrupt:
            logger.warning("[SYSTEM] Stopping pipeline...")
        finally:
            self.stop()
            
        return self.chord_objects

    # Stop the pipeline
    def stop(self):
        self.is_running = False

        # Stop playback first
        if self.playback: self.playback.stop()
        
        # Stop conductor
        if self.conductor: self.conductor.stop()

        # Stop listeners / synth
        if self.midi_listener: self.midi_listener.stop()
        if self.synth_listener: self.synth_listener.stop()
        if self.synth: self.synth.cleanup()

        # Join threads
        if self.playback and self.playback.is_alive():
            try: self.playback.join(timeout=1.0)
            except: pass
        if self.metronome_thread and self.metronome_thread.is_alive():
            try: self.metronome_thread.join(timeout=1.0)
            except: pass
        if self.timing_thread and self.timing_thread.is_alive():
            try: self.timing_thread.join(timeout=1.0)
            except: pass

        # Shutdown predictor
        try:
            self.predictor.close()
        except Exception as e:
            logger.error(f"[SYSTEM] Predictor shutdown error: {e}")

        # Save latency metrics to JSON file
        try:
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = logs_dir / f"latency_metrics_{timestamp}.json"
            
            with open(filename, 'w') as f:
                json.dump(self.perf_metrics, f, indent=4)
            
            logger.info(f"[METRICS] Saved {len(self.perf_metrics)} metrics to {filename}")
        except Exception as e:
            logger.error(f"[METRICS] Failed to save metrics: {e}")

    # Get the current sequence of chords
    def get_current_sequence(self) -> List[str]:
        if not self.chord_objects: return []
        return [compact_chord(c.root, c.chord_type) for c in self.chord_objects]
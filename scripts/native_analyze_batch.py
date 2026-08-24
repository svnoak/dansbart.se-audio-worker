"""Runs the real AudioAnalyzer (needs Essentia) against a folder of MP3s
named <track_id>.mp3 (the naming ml-trainer/tuner/download_audio.py
already uses), and writes one JSON file per track containing the raw
artifacts -- the same shape stored in production's analysis_sources.raw_data.

This only does extraction. It never touches any database. A separate
script (ml-trainer/tuner/import_native_analysis.py) reads this output
and inserts it into the trainer's local SQLite -- that script runs
outside Docker, since it needs no Essentia.

Must run inside the audio-worker image (linux/amd64, has Essentia) --
see dansbart-audio-worker/scripts/local_diagnose.sh for the same Docker
pattern. Example:

    docker run --rm --platform linux/amd64 \\
      -v "$NECKENML_DIR/packages/neckenml-core/src/neckenml/core:$SITE_PACKAGES/neckenml/core" \\
      -v "$NECKENML_DIR/packages/neckenml-analyzer/src/neckenml/analyzer:$SITE_PACKAGES/neckenml/analyzer" \\
      -v "$SCRIPT_DIR/native_analyze_batch.py:/app/native_analyze_batch.py" \\
      -v "/path/to/audio_cache:/app/audio_cache" \\
      -v "/path/to/native_analysis_out:/app/native_analysis_out" \\
      --user root \\
      dansbart-audio-worker-local \\
      python /app/native_analyze_batch.py /app/audio_cache /app/native_analysis_out
"""

import json
import os
import sys

from neckenml.analyzer.audio_analyzer import AudioAnalyzer


def main():
    if len(sys.argv) < 3:
        print("Usage: python native_analyze_batch.py <input_mp3_dir> <output_json_dir>")
        sys.exit(1)

    input_dir, output_dir = sys.argv[1], sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)

    mp3_files = sorted(f for f in os.listdir(input_dir) if f.endswith(".mp3"))
    print(f"{len(mp3_files)} MP3 files to analyze")

    with AudioAnalyzer(model_dir="/app/models") as analyzer:
        for i, filename in enumerate(mp3_files):
            track_id = filename[:-4]  # strip .mp3
            out_path = os.path.join(output_dir, f"{track_id}.json")
            if os.path.exists(out_path):
                print(f"[{i+1}/{len(mp3_files)}] skip (already analyzed) {track_id}")
                continue

            print(f"[{i+1}/{len(mp3_files)}] analyzing {track_id}...")
            try:
                result = analyzer.analyze_file(
                    os.path.join(input_dir, filename), return_artifacts=True
                )
            except Exception as e:
                print(f"  FAILED: {e}")
                continue

            with open(out_path, "w") as f:
                json.dump(result, f)

    print("Done.")


if __name__ == "__main__":
    main()

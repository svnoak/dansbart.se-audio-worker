"""Standalone check for the rms/zcr/onset_rate bug in
neckenml.analyzer.audio_analyzer.AudioAnalyzer._extract_lightweight_features.

That method has returned [0.0, 0.0, 0.0] for every real track seen so
far. The real exception was never logged before, so the cause is
unknown. This script loads one audio file and calls the method
directly, skipping beat tracking, MusiCNN, and vocal detection, so it
runs in seconds instead of minutes. The method's own exception handler
now prints the real traceback -- read that output, not this script, to
find the cause.

Run inside the audio-worker container (needs Essentia, linux/amd64):
    python scripts/diagnose_lightweight_features.py /app/test_audio/track.mp3
"""

import sys

import essentia.standard as es

from neckenml.analyzer.audio_analyzer import AudioAnalyzer


def main():
    if len(sys.argv) < 2:
        print("Usage: python diagnose_lightweight_features.py <audio_file> [<audio_file> ...]")
        sys.exit(1)

    with AudioAnalyzer(model_dir="/app/models") as analyzer:
        for path in sys.argv[1:]:
            print(f"\n--- {path} ---")
            loader = es.MonoLoader(filename=path, sampleRate=16000, resampleQuality=4)
            audio_16k = loader()
            rms, zcr, onset_rate = analyzer._extract_lightweight_features(audio_16k)
            print(f"rms={rms}  zcr={zcr}  onset_rate={onset_rate}")
            if (rms, zcr, onset_rate) == (0.0, 0.0, 0.0):
                print("Still zero -- check the [WARNING] line and traceback above for the real cause.")


if __name__ == "__main__":
    main()

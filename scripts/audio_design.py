"""Deterministic tone composition; all audio is synthesized locally."""
import io
import math
import struct
import wave

PRESETS = {
    "completion": {"notes": [784, 587.33], "note_ms": 300, "gap_ms": 50},
    "approval": {"notes": [587.33, 784], "note_ms": 300, "gap_ms": 50},
}


def validate_design(design):
    if not isinstance(design, dict) or set(design) != {"notes", "note_ms", "gap_ms"}:
        raise ValueError("design requires notes, note_ms, gap_ms")
    notes = design["notes"]
    if not isinstance(notes, list) or not 1 <= len(notes) <= 4:
        raise ValueError("use 1 to 4 notes")
    for note in notes:
        if type(note) not in (int, float) or not math.isfinite(note) or not 160 <= note <= 1600:
            raise ValueError("note frequency must be 160..1600 Hz")
    for key, lo, hi in (("note_ms", 120, 400), ("gap_ms", 0, 200)):
        if type(design[key]) is not int or not lo <= design[key] <= hi:
            raise ValueError(f"{key} must be an integer {lo}..{hi}")
    return design


def render(event, volume=.22, tone="soft", design=None):
    if event not in PRESETS or tone not in ("soft", "bell"):
        raise ValueError("unknown event or tone")
    if type(volume) not in (int, float) or not math.isfinite(volume) or not 0 <= volume <= 1:
        raise ValueError("volume must be 0..1")
    if design is None:
        design = PRESETS[event]
        if tone == "bell":
            design = {"notes": [1046.5 if event == "completion" else 1318.5], "note_ms": 400, "gap_ms": 0}
    validate_design(design)
    rate = 22050
    notes = design["notes"]
    duration, gap = design["note_ms"] / 1000, design["gap_ms"] / 1000
    total = len(notes) * duration + (len(notes) - 1) * gap
    pcm = bytearray()
    for i in range(round(total * rate)):
        t = i / rate
        index = min(len(notes) - 1, int(t / (duration + gap)))
        s = t - index * (duration + gap)
        value = 0
        if 0 <= s < duration:
            envelope = (1 - math.exp(-s / .018)) * math.exp(-s / (duration * .38))
            envelope *= min(1, max(0, (duration - s) / .04))
            phase = 2 * math.pi * notes[index] * s
            overtone = .12 if tone == "soft" else .25
            value = envelope * (math.sin(phase) + overtone * math.sin(2 * phase))
        pcm.extend(struct.pack("<h", round(max(-1, min(1, value * volume * .67)) * 32767)))
    result = io.BytesIO()
    with wave.open(result, "wb") as w:
        w.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        w.writeframes(pcm)
    return result.getvalue()

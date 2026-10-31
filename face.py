#!/usr/bin/env python3
"""
Pixel face for a costume screen.
- Idle face: blinks, glances around, bobs slightly.
- Each button = an emotion. Tap it and the emotion shows for HOLD_SECONDS
  (or stays as long as you hold the button, then lingers HOLD_SECONDS).

Buttons: wire each button between a GPIO pin and GND. No resistors needed
(the Pi's internal pull-ups are used).
Keyboard keys 1-6 also work (for testing, or for an RP2040 acting as a USB keyboard).
Esc or Q quits.
"""
import math
import os
import random
import struct
import time
import wave

import pygame

# ---------------- settings you can tweak ----------------
HOLD_SECONDS = 5.0      # how long an emotion stays after you let go
SOUND_ON = True
SOUND_VOLUME = 0.6      # 0.0 to 1.0
PIXEL_GAP = 0.15        # gap between "LEDs" (0 = solid pixels, 0.3 = very dotty)
FPS = 30
FULLSCREEN = True
ROTATE = 90             # 0, 90, 180 or 270. Use 90 or 270 to turn a portrait screen sideways
                        # (if the face is upside down, switch 90 <-> 270)

# GPIO (BCM numbers) -> emotion. Each pin sits right next to a GND pin.
#   GPIO5  = physical pin 29   (GND on pin 30)
#   GPIO6  = physical pin 31   (GND on pin 30/34)
#   GPIO13 = physical pin 33   (GND on pin 34)
#   GPIO19 = physical pin 35   (GND on pin 34/39)
#   GPIO26 = physical pin 37   (GND on pin 39)
#   GPIO21 = physical pin 40   (GND on pin 39)
BUTTONS = {
    5: "happy",
    6: "sad",
    13: "angry",
    19: "shocked",
    26: "love",
    21: "sleepy",
}
KEYS = {
    pygame.K_1: "happy",
    pygame.K_2: "sad",
    pygame.K_3: "angry",
    pygame.K_4: "shocked",
    pygame.K_5: "love",
    pygame.K_6: "sleepy",
}

COLORS = {
    "idle":    (0, 220, 255),
    "happy":   (255, 220, 0),
    "sad":     (60, 120, 255),
    "angry":   (255, 40, 30),
    "shocked": (255, 255, 255),
    "love":    (255, 70, 170),
    "sleepy":  (150, 110, 255),
}
TEAR = (120, 200, 255)

# ---------------- pixel art ----------------
# '#' = face color, 'b' = tear blue, '.' = off.
# Eyes are drawn for the LEFT eye; the right eye is mirrored automatically.
EYES = {
    "idle": """
..####..
.######.
########
########
########
########
.######.
..####..""",
    "blink": """
........
........
........
########
########
........
........
........""",
    "happy": """
........
...##...
..####..
.##..##.
##....##
#......#
........
........""",
    "sad": """
........
......##
....####
..######
########
.######.
..####b.
......b.""",
    "angry": """
##......
####....
######..
########
########
.######.
..####..
........""",
    "shocked": """
..####..
.#....#.
#......#
#..##..#
#..##..#
#......#
.#....#.
..####..""",
    "love": """
........
.##..##.
########
########
.######.
..####..
...##...
........""",
    "sleepy": """
........
........
........
........
#......#
.######.
........
........""",
}

MOUTHS = {
    "idle": """
................
.##..........##.
...##########...
................""",
    "happy": """
################
.##############.
..############..
....########....""",
    "sad": """
................
....########....
..##........##..
.##..........##.""",
    "angry": """
################
#..#..#..#..#..#
################
................""",
    "shocked": """
.....######.....
....##....##....
....##....##....
.....######.....""",
    "love": """
##............##
.##..........##.
..############..
................""",
    "sleepy": """
................
......####......
.....#....#.....
......####......""",
}

# ---------------- arcade sounds ----------------
# Each sound is a list of notes: N(wave, start_hz, end_hz, seconds, volume, duty, vibrato_hz, vibrato_depth)
# wave = "square", "triangle", "noise", or "rest". start != end makes a pitch sweep.
def N(wave, f0, f1, dur, vol=0.5, duty=0.5, vr=0.0, vd=0.0):
    return (wave, f0, f1, dur, vol, duty, vr, vd)


SOUNDS = {
    # 1-up / power-up: fast rising arpeggio
    "happy": [N("square", 523, 523, .07), N("square", 659, 659, .07), N("square", 784, 784, .07),
              N("square", 1047, 1047, .07), N("square", 1319, 1319, .07), N("square", 1568, 1568, .22)],
    # sad trombone, chip style
    "sad": [N("square", 392, 392, .28, .5, .25), N("square", 370, 370, .28, .5, .25),
            N("square", 349, 349, .28, .5, .25), N("square", 330, 330, .9, .5, .25, 6, .02)],
    # growl + crunch + low buzzy stomp
    "angry": [N("square", 220, 90, .18, .6, .125), N("noise", 3000, 3000, .08, .5),
              N("square", 131, 131, .07, .6, .125), N("square", 110, 110, .07, .6, .125),
              N("square", 131, 131, .07, .6, .125), N("square", 82, 82, .3, .6, .125, 20, .05)],
    # "boi-oing!" alert
    "shocked": [N("square", 200, 1600, .15, .5), N("triangle", 1600, 1600, .35, .6, .5, 14, .06)],
    # sparkly pickup with a quieter echo
    "love": [N("triangle", 988, 988, .07, .6), N("triangle", 1319, 1319, .07, .6), N("triangle", 1661, 1661, .07, .6),
             N("triangle", 1976, 1976, .14, .6), N("rest", 1, 1, .05),
             N("square", 1661, 1661, .06, .2, .25), N("square", 1976, 1976, .12, .2, .25)],
    # slow power-down yawn, then two soft "zzz"
    "sleepy": [N("triangle", 700, 180, .7, .6, .5, 4, .03), N("rest", 1, 1, .15),
               N("noise", 900, 900, .25, .15), N("rest", 1, 1, .12), N("noise", 700, 700, .3, .12)],
}

SAMPLE_RATE = 22050


def synth(notes):
    """Turn a note list into 16-bit mono samples, crushed to a few levels for that chip sound."""
    out = []
    phase = 0.0
    noise_val = 0.0
    rng = random.Random(1)
    for wave_type, f0, f1, dur, vol, duty, vr, vd in notes:
        n = int(dur * SAMPLE_RATE)
        fade = 0.004 * SAMPLE_RATE
        for i in range(n):
            if wave_type == "rest":
                out.append(0)
                continue
            t = i / SAMPLE_RATE
            f = f0 if f0 == f1 else f0 * (f1 / f0) ** (t / dur)
            if vd:
                f *= 1 + vd * math.sin(2 * math.pi * vr * t)
            prev = phase
            phase = (phase + f / SAMPLE_RATE) % 1.0
            if wave_type == "square":
                s = 1.0 if phase < duty else -1.0
            elif wave_type == "triangle":
                s = 4 * abs(phase - 0.5) - 1
            else:  # noise: new random value every cycle
                if phase < prev:
                    noise_val = rng.uniform(-1, 1)
                s = noise_val
            env = 1 - 0.5 * (t / dur)
            edge = min(1.0, i / fade, (n - i) / fade)
            s = round(s * env * edge * 7) / 7
            out.append(int(s * vol * 0.8 * 32767))
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
    return out


def make_sound_files():
    """Generate sounds/<emotion>.wav next to this script. Returns {emotion: path}."""
    if not SOUND_ON:
        return {}
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
    os.makedirs(folder, exist_ok=True)
    paths = {}
    for emo, notes in SOUNDS.items():
        path = os.path.join(folder, f"{emo}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            samples = synth(notes)
            w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        paths[emo] = path
    return paths


# The audio device is only opened while a sound plays, then closed again.
# Keeping it open while silent makes some speakers thump.
audio = {"sound": None, "close_at": 0.0}


def play_sound(path):
    try:
        if pygame.mixer.get_init():
            pygame.mixer.stop()
        else:
            pygame.mixer.init()
        snd = pygame.mixer.Sound(path)
        snd.set_volume(SOUND_VOLUME)
        snd.play()
        audio["sound"] = snd
        audio["close_at"] = time.monotonic() + snd.get_length() + 0.5
    except pygame.error as e:
        print(f"Sound failed ({e})")


def close_audio_when_done():
    if pygame.mixer.get_init() and time.monotonic() > audio["close_at"] and not pygame.mixer.get_busy():
        pygame.mixer.quit()
        audio["sound"] = None


CANVAS_W, CANVAS_H = 40, 24   # logical "LED" grid
LEFT_EYE_X, RIGHT_EYE_X, EYE_Y = 7, 25, 4
MOUTH_X, MOUTH_Y = 12, 16


def parse(art):
    return [row for row in art.strip("\n").split("\n")]


EYES = {k: parse(v) for k, v in EYES.items()}
MOUTHS = {k: parse(v) for k, v in MOUTHS.items()}


def stamp(grid, sprite, x0, y0, mirror=False):
    for y, row in enumerate(sprite):
        if mirror:
            row = row[::-1]
        for x, ch in enumerate(row):
            gx, gy = x0 + x, y0 + y
            if ch != "." and 0 <= gx < CANVAS_W and 0 <= gy < CANVAS_H:
                grid[gy][gx] = ch


def build_face(emotion, blinking, look_dx, look_dy, bob):
    grid = [["." for _ in range(CANVAS_W)] for _ in range(CANVAS_H)]
    eye = EYES["blink"] if blinking else EYES[emotion]
    stamp(grid, eye, LEFT_EYE_X + look_dx, EYE_Y + look_dy + bob)
    stamp(grid, eye, RIGHT_EYE_X + look_dx, EYE_Y + look_dy + bob, mirror=True)
    stamp(grid, MOUTHS[emotion], MOUTH_X, MOUTH_Y + bob)
    return grid


def draw(screen, grid, color):
    sw, sh = screen.get_size()
    cell = min(sw / CANVAS_W, sh / CANVAS_H)
    ox = (sw - cell * CANVAS_W) / 2
    oy = (sh - cell * CANVAS_H) / 2
    gap = cell * PIXEL_GAP
    size = max(1, math.ceil(cell - gap))
    screen.fill((0, 0, 0))
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            c = TEAR if ch == "b" else color
            screen.fill(c, (int(ox + x * cell), int(oy + y * cell), size, size))


# ---------------- input ----------------
state = {"emotion": None, "until": 0.0, "held": set(), "play": None}


def trigger(emotion, sound=False):
    state["emotion"] = emotion
    state["until"] = time.monotonic() + HOLD_SECONDS
    if sound:
        state["play"] = emotion  # played by the main loop


def setup_gpio():
    try:
        from gpiozero import Button
    except ImportError:
        print("gpiozero not found, keyboard only")
        return []
    buttons = []
    for pin, emo in BUTTONS.items():
        try:
            b = Button(pin, pull_up=True, bounce_time=0.03)
        except Exception as e:  # not on a Pi, or pin busy
            print(f"GPIO{pin} unavailable ({e}), keyboard only")
            return buttons
        b.when_pressed = lambda e=emo: (state["held"].add(e), trigger(e, sound=True))
        b.when_released = lambda e=emo: (state["held"].discard(e), trigger(e))
        buttons.append(b)
    return buttons


def main():
    pygame.display.init()   # not pygame.init(), which would open the audio device right away
    flags = pygame.FULLSCREEN if FULLSCREEN else 0
    screen = pygame.display.set_mode((0, 0) if FULLSCREEN else (800, 480), flags)
    pygame.display.set_caption("face")
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()
    # draw onto a canvas in the rotated orientation, then rotate it onto the real screen
    sw, sh = screen.get_size()
    canvas = pygame.Surface((sh, sw) if ROTATE in (90, 270) else (sw, sh))
    buttons = setup_gpio()  # keep reference so buttons aren't garbage collected
    sounds = make_sound_files()

    next_blink = time.monotonic() + random.uniform(2, 5)
    blink_end = 0.0
    look = (0, 0)
    next_look = time.monotonic() + random.uniform(1.5, 4)

    running = True
    while running:
        now = time.monotonic()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif ev.key in KEYS:
                    state["held"].add(KEYS[ev.key])
                    trigger(KEYS[ev.key], sound=True)
            elif ev.type == pygame.KEYUP and ev.key in KEYS:
                state["held"].discard(KEYS[ev.key])
                trigger(KEYS[ev.key])

        # play a queued sound, and close the audio device once it's finished
        if state["play"]:
            path = sounds.get(state["play"])
            state["play"] = None
            if path:
                play_sound(path)
        close_audio_when_done()

        # which emotion is showing?
        if state["emotion"] and (state["emotion"] in state["held"] or now < state["until"]):
            emotion = state["emotion"]
        else:
            emotion = "idle"
            state["emotion"] = None

        # blinking (idle + a few emotions)
        if now >= next_blink:
            blink_end = now + 0.12
            next_blink = now + random.uniform(2.5, 5.5)
        blinking = now < blink_end and emotion in ("idle", "sad", "love", "angry")

        # glancing around (idle only)
        if emotion == "idle":
            if now >= next_look:
                look = random.choice([(0, 0), (0, 0), (-2, 0), (2, 0), (-1, -1), (1, -1)])
                next_look = now + random.uniform(1.0, 3.5)
            dx, dy = look
        else:
            dx, dy = 0, 0

        # bobbing / per-emotion motion
        bob = round(math.sin(now * 2.0) * 0.6)
        if emotion == "angry":
            dx += random.choice((-1, 0, 1))       # shake
        elif emotion == "shocked":
            bob = -1                               # jump up
        elif emotion == "happy":
            bob = round(math.sin(now * 8) * 0.6)   # bouncy

        draw(canvas, build_face(emotion, blinking, dx, dy, bob), COLORS[emotion])
        screen.blit(pygame.transform.rotate(canvas, ROTATE) if ROTATE else canvas, (0, 0))
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
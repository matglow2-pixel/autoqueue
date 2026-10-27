"""Calibrated, position-specific screen checks and like-button matching."""
import cv2
import numpy as np
from PIL import Image

from .engine import View


def array(image):
    return np.asarray(image.convert("RGB"))


def patch_matches(frame, box, template, tolerance=18):
    x1, y1, x2, y2 = box
    patch = frame[y1:y2, x1:x2]
    if patch.shape != template.shape or not patch.size:
        return False
    error = np.abs(patch.astype(np.int16) - template.astype(np.int16))
    # Require broad agreement, so a single changed word/button is significant.
    return float(error.mean()) <= tolerance and float(np.percentile(error, 90)) <= 55


class Recognizer:
    def __init__(self, folder, config):
        self.config = config
        self.templates = {}
        for role, data in config.items():
            self.templates[role] = {
                name: array(Image.open(folder / item["file"]))
                for name, item in data["markers"].items()
            }

    def inspect(self, role, image):
        frame = array(image)
        data = self.config[role]
        hits = [name for name, item in data["markers"].items()
                if name != "like" and patch_matches(
                    frame, item["box"], self.templates[role][name])]
        # The member stays on the world map while matchmaking.
        if "queue" in hits and "world" in hits:
            hits.remove("world")
        # Ambiguous recognition is never permission to click.
        state = hits[0] if len(hits) == 1 else "unknown"
        return View(state, self.find_likes(role, frame) if state == "results" else [])

    def find_likes(self, role, frame):
        template = self.templates[role]["like"]
        h, w = template.shape[:2]
        # Restrict search to the calibrated button row, avoiding other UI icons.
        box = self.config[role]["markers"]["like"]["box"]
        top, bottom = max(0, box[1] - 15), min(frame.shape[0], box[3] + 15)
        area = frame[top:bottom]
        if area.shape[0] < h or area.shape[1] < w:
            return []
        scores = cv2.matchTemplate(area, template, cv2.TM_SQDIFF_NORMED)
        found = []
        for _ in range(5):
            score, _, (x, y), _ = cv2.minMaxLoc(scores)
            if score > 0.025:
                break
            if patch_matches(area, (x, y, x + w, y + h), template, tolerance=15):
                found.append((x + w // 2, top + y + h // 2))
            scores[max(0, y - h // 2):y + h // 2 + 1,
                   max(0, x - w // 2):x + w // 2 + 1] = 1
        return found

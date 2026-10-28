"""Offline OCR for labels; automatic geometry for the unlabelled game icons."""
from dataclasses import dataclass, replace
import re
import time

import cv2
import numpy as np

from .engine import View


@dataclass(frozen=True)
class Text:
    value: str
    box: tuple[int, int, int, int]
    confidence: float

    @property
    def key(self):
        return re.sub(r"[^a-z0-9]", "", self.value.lower())

    @property
    def center(self):
        x1, y1, x2, y2 = self.box
        return (x1 + x2) // 2, (y1 + y2) // 2


class Recognizer:
    def __init__(self, reader=None):
        if reader is None:
            from rapidocr_onnxruntime import RapidOCR
            # Models ship inside the Python wheel: no Tesseract or model setup.
            reader = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1,
                              det_limit_side_len=960, det_limit_type="max")
        self.reader = reader
        self.cache = {}

    def inspect(self, image, role="default"):
        full = np.asarray(image.convert("RGB"))
        frame, offset = game_frame(full)
        if frame is None:
            return View(detail="Use portrait game windows, both fully visible.")
        # Results icons have no text. Detect the divider and button row directly
        # on each fresh frame, including the dark/gold already-liked state.
        result_view = results_fast(frame)
        if result_view is not None:
            self.cache.pop(role, None)
            return translate(result_view, offset)
        cached = self.cache.get(role)
        if cached and cached[0] == frame.shape and time.monotonic() - cached[1] < 10:
            _, _, view, anchors = cached
            if (all(anchor_matches(frame, box, patch) for box, patch in anchors)
                    and (view.state != "accept" or button_color_fraction(
                        frame, view.targets["accept"], yellow=True) > .25)):
                return translate(view, offset)
        # Read only controls/minimap labels first. Hero art and chat no longer
        # pass through OCR on every initial button read.
        atlas, regions = control_atlas(frame)
        result, _ = self.reader(cv2.cvtColor(atlas, cv2.COLOR_RGB2BGR), use_cls=False)
        texts = []
        for item in read_texts(result):
            for start, end, box in regions:
                x1, y1, x2, y2 = item.box
                left, top, right, _ = box
                if start <= y1 <= y2 <= end and 0 <= x1 <= x2 <= right - left:
                    texts.append(Text(item.value, (x1 + left, y1 - start + top,
                                                  x2 + left, y2 - start + top), item.confidence))
                    break
        view = classify(frame, texts)
        if view.state == "unknown":
            # Full-frame OCR is a fallback, not a prerequisite for clicking.
            result, _ = self.reader(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), use_cls=False)
            for item in read_texts(result):
                duplicates = [t for t in texts if t.key == item.key
                              and abs(t.center[0] - item.center[0]) < 20
                              and abs(t.center[1] - item.center[1]) < 20]
                if not duplicates:
                    texts.append(item)
                elif item.confidence > max(t.confidence for t in duplicates):
                    texts = [t for t in texts if t not in duplicates] + [item]
            view = classify(frame, texts)
        self.cache.pop(role, None)
        if view.state in {"world", "menu", "queue", "accept"}:
            anchors = cache_anchors(frame, view.state, texts)
            if len(anchors) >= 2 or (view.state == "queue" and anchors):
                self.cache[role] = (frame.shape, time.monotonic(), view, anchors)
        return translate(view, offset)


def control_atlas(frame):
    h, w = frame.shape[:2]
    if yellow_button_present(frame):
        boxes = [(0, int(.65 * h), w, h)]
    else:
        boxes = [(0, int(.72 * h), w, h),
                 (int(.64 * w), int(.16 * h), w, int(.36 * h)),
                 (0, int(.22 * h), int(.34 * w), int(.45 * h))]
    height = sum(y2 - y1 + 12 for _, y1, _, y2 in boxes)
    atlas = np.zeros((height, w, 3), np.uint8)
    regions = []
    start = 0
    for x1, y1, x2, y2 in boxes:
        end = start + y2 - y1
        atlas[start:end, :x2-x1] = frame[y1:y2, x1:x2]
        regions.append((start, end, (x1, y1, x2, y2)))
        start = end + 12
    return atlas, regions


def read_texts(result, dy=0):
    texts = []
    for polygon, value, confidence in result or []:
        points = np.asarray(polygon)
        x1, y1 = points.min(axis=0).astype(int)
        x2, y2 = points.max(axis=0).astype(int)
        texts.append(Text(value, (int(x1), int(y1) + dy, int(x2), int(y2) + dy), float(confidence)))
    return texts


def translate(view, offset):
    dx, dy = offset
    return replace(view, targets={k: (x + dx, y + dy) for k, (x, y) in view.targets.items()},
                   likes=[(x + dx, y + dy) for x, y in view.likes])


def cache_anchors(frame, state, texts):
    """Keep only automatically read UI labels, never animated game artwork."""
    keys = {"world": ("demonsea", "explore"), "menu": ("match", "team"),
            "queue": ("cancel", "team", "matchmaking", "demonsea"),
            "accept": ("accept", "decline")}[state]
    h, w = frame.shape[:2]
    anchors = []
    for text in texts:
        if text.confidence < .65 or not any(k in text.key for k in keys):
            continue
        # Mirror the spatial guards used for OCR scene classification.
        x, y = text.center
        valid = (("demonsea" in text.key and y < .36 * h)
                 or ("explore" in text.key and y > .85 * h)
                 or ("matchmaking" in text.key and x < .35 * w and y < .5 * h)
                 or (text.key in {"match", "cancel", "accept", "decline"} and y > .65 * h)
                 or ("team" in text.key and x < .6 * w and y > .65 * h))
        if not valid:
            continue
        x1, y1, x2, y2 = text.box
        box = (max(0, x1 - 2), max(0, y1 - 2), min(w, x2 + 2), min(h, y2 + 2))
        a, b, c, d = box
        if c > a and d > b:
            anchors.append((box, frame[b:d, a:c].copy()))
    return anchors


def anchor_matches(frame, box, template):
    x1, y1, x2, y2 = box
    patch = frame[y1:y2, x1:x2]
    if patch.shape != template.shape:
        return False
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    ref = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY)
    if float(ref.std()) < 8:
        return False  # A blank patch is not a recognizable label.
    score = cv2.matchTemplate(gray, ref, cv2.TM_CCOEFF_NORMED)[0, 0]
    return score > .92 and np.abs(patch.astype(np.int16) - template.astype(np.int16)).mean() < 24


def game_frame(frame):
    """Find a portrait viewport, including games centered in landscape players."""
    h, w = frame.shape[:2]
    if .4 <= w / h <= .8:
        return frame, (0, 0)
    mask = np.mean(frame[int(h * .1):int(h * .9)].max(axis=2) > 35, axis=0) > .45
    edges = np.diff(np.r_[False, mask, False].astype(int))
    spans = [(a, b) for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
             if .4 <= (b - a) / h <= .8]
    if not spans:
        return None, (0, 0)
    left, right = max(spans, key=lambda span: span[1] - span[0])
    return frame[:, left:right], (int(left), 0)


def classify(frame, texts):
    h, w = frame.shape[:2]
    words = [t for t in texts if t.confidence >= .65]

    def find(key, region=(0, 0, 1, 1), contains=False):
        x1, y1, x2, y2 = region
        hits = [t for t in words if (key in t.key if contains else key == t.key)
                and x1 * w < t.center[0] < x2 * w
                and y1 * h < t.center[1] < y2 * h]
        return hits[0] if len(hits) == 1 else None

    title = find("demonsea", (0, 0, 1, .36), contains=True)
    accept = find("accept", (.4, .65, 1, .99))
    decline = find("decline", (0, .65, .6, .99))
    drops = find("drops", (0, .45, .5, .88))
    match = find("match", (.4, .65, 1, .96))
    cancel = find("cancel", (.4, .65, 1, .96))
    team = find("team", (0, .65, .6, .96), contains=True)
    matchmaking = find("matchmaking", (0, 0, .35, .5), contains=True)

    if (accept and decline and abs(accept.center[1] - decline.center[1]) < .04 * h
            and (title or button_pair_colors(frame, decline.center, accept.center))):
        if button_color_fraction(frame, accept.center, yellow=True) > .25:
            return View("accept", targets={"accept": accept.center})
        return View("accepted", detail="Accept is disabled; waiting for the other players.")
    if title and drops:
        return results_layout(frame, drops.box[3] + int(.006 * h))
    if cancel and team:
        return View("queue", detail="Waiting for a match; Accept is monitored.")
    if match and team and (title or button_pair_colors(frame, team.center, match.center)):
        return View("menu", targets={"match": match.center})
    if matchmaking:
        return View("queue", detail="Waiting for a match; Accept is monitored.")
    # Restrict the world label to the minimap and require its bottom action too.
    explore = next((t for t in words if "explore" in t.key and t.center[1] > .85 * h), None)
    if title and title.center[0] > .55 * w and explore:
        # The dungeon has no text label in-world. Its large entrance occupies
        # this relative area in the supplied Demonseal Gorge layout.
        return View("world", targets={"dungeon": (round(.52 * w), round(.35 * h))})
    return View(detail="Waiting for the next game screen (combat/loading is normal).")


def button_pair_colors(frame, left, right):
    """White left pill + yellow right pill provide context if title OCR fails."""
    return (button_color_fraction(frame, left, yellow=False) > .25
            and button_color_fraction(frame, right, yellow=True) > .25)


def button_color_fraction(frame, point, yellow):
    h, w = frame.shape[:2]
    x, y = point
    area = frame[max(0, y - int(.02 * h)):min(h, y + int(.02 * h)),
                 max(0, x - int(.12 * w)):min(w, x + int(.12 * w))]
    if not area.size:
        return 0.0
    hsv = cv2.cvtColor(area, cv2.COLOR_RGB2HSV)
    if yellow:
        mask = ((hsv[:, :, 0] > 15) & (hsv[:, :, 0] < 60)
                & (hsv[:, :, 1] > 65) & (hsv[:, :, 2] > 140))
    else:
        mask = (hsv[:, :, 1] < 65) & (hsv[:, :, 2] > 170)
    return float(mask.mean())


def yellow_button_present(frame):
    h, w = frame.shape[:2]
    area = frame[int(.65 * h):, int(.4 * w):]
    hsv = cv2.cvtColor(area, cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 0] > 15) & (hsv[:, :, 0] < 60)
            & (hsv[:, :, 1] > 65) & (hsv[:, :, 2] > 140)).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return any(.2 * w < bw < .55 * w and .02 * h < bh < .1 * h and bw / bh > 2.3
               for _, _, bw, bh in (cv2.boundingRect(c) for c in contours))


def find_likes(frame, drops_y, min_buttons=1):
    """Read both white unclicked pills and dark pills with gold thumbs/borders."""
    h, w = frame.shape[:2]
    top, bottom = max(0, int(drops_y - .15 * h)), max(0, int(drops_y - .008 * h))
    if bottom <= top:
        return [], False
    area = frame[top:bottom]
    hsv = cv2.cvtColor(area, cv2.COLOR_RGB2HSV)
    white = (hsv[:, :, 1] < 65) & (hsv[:, :, 2] > 165)
    gold = (hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 55) & (hsv[:, :, 1] > 40) & (hsv[:, :, 2] > 60)
    buttons = []
    kernel = np.ones((3, 3), np.uint8)
    for mask, is_white in ((white, True), (gold, False)):
        binary = cv2.morphologyEx(mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, bw, bh = cv2.boundingRect(contour)
            if not (.065 * w <= bw <= .17 * w and .012 * h <= bh <= .045 * h
                    and 1.7 < bw / bh < 3.8 and cv2.contourArea(contour) / (bw * bh) > .60):
                continue
            icon = hsv[y + bh // 5:y + 4 * bh // 5, x + bw // 4:x + 3 * bw // 4]
            if not icon.size:
                continue
            dark = float(np.mean(icon[:, :, 2] < 125))
            colored = float(np.mean((icon[:, :, 1] > 80) & (icon[:, :, 2] > 125)))
            if dark < .02 and colored < .04:
                continue
            point = (x + bw // 2, top + y + bh // 2)
            if any(abs(point[0] - p[0]) < .035 * w and abs(point[1] - p[1]) < .015 * h for p, _ in buttons):
                continue
            buttons.append((point, is_white and colored < .08 and dark > .02))
    if not min_buttons <= len(buttons) <= 4:
        return [], False
    if max(p[0][1] for p in buttons) - min(p[0][1] for p in buttons) > .018 * h:
        return [], False
    return [p for p, unclicked in buttons if unclicked], True


def find_return(frame):
    """Find the white left chevron in the lower-left results corner."""
    h, w = frame.shape[:2]
    top, right = int(.86 * h), int(.25 * w)
    hsv = cv2.cvtColor(frame[top:, :right], cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 185)).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hits = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if not (.015 * w < bw < .1 * w and .016 * h < bh < .065 * h and .3 < bw / bh < 1.1):
            continue
        component = np.zeros((bh, bw), np.uint8)
        cv2.drawContours(component, [contour - (x, y)], -1, 255, -1)
        if is_left_chevron(component):
            hits.append((x + bw // 2, top + y + bh // 2))
    return hits[0] if len(hits) == 1 else None


def is_left_chevron(component):
    """Compare normalized silhouettes, allowing different arrow stroke widths."""
    sample = cv2.resize(component, (32, 48), interpolation=cv2.INTER_AREA) > 100
    for inner in (.35, .5, .65):
        reference = np.zeros((48, 32), np.uint8)
        points = np.array([(22, 0), (0, 24), (22, 47), (31, 38),
                           (round(inner * 31), 24), (31, 9)], np.int32)
        cv2.fillPoly(reference, [points], 1)
        ref = reference.astype(bool)
        overlap = np.logical_and(sample, ref).sum() / np.logical_or(sample, ref).sum()
        if overlap > .60:
            return True
    return False


def results_layout(frame, divider_y):
    """Target actual unclicked thumbs, followed by the bottom-left exit area."""
    h, w = frame.shape[:2]
    points = find_like_icons(frame, divider_y)
    targets = {f"like_{i + 1}": p for i, p in enumerate(points)}
    targets["return"] = find_return(frame) or (round(.11 * w), round(.955 * h))
    ready = bool(points)
    detail = (f"{len(points)} thumbs-up icons; verify likes before Exit." if points else
              "No white thumbs detected; waiting for clicked-button confirmation.")
    return View("results", points, targets, ready, detail)


def find_like_icons(frame, divider_y):
    """White rounded buttons with dark thumbs; never gold own-player counters."""
    h, w = frame.shape[:2]
    top = max(0, round(divider_y - .22 * h))
    bottom = min(h, round(divider_y - .008 * h))
    if bottom <= top:
        return []
    area = frame[top:bottom]
    hsv = cv2.cvtColor(area, cv2.COLOR_RGB2HSV)
    white = ((hsv[:, :, 1] < 95) & (hsv[:, :, 2] > 125)).astype(np.uint8) * 255
    closed = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    expected_y = divider_y - .11 * w
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        fill = cv2.contourArea(contour) / (bw * bh)
        coverage = np.mean(white[y:y+bh, x:x+bw] > 0)
        if not (.045 * w < bw < .20 * w and .012 * h < bh < .065 * h
                and 1.6 < bw / bh < 5 and fill > .55 and coverage > .55):
            continue
        center = hsv[y + bh // 5:y + 4 * bh // 5, x + bw // 4:x + 3 * bw // 4]
        dark = np.mean(center[:, :, 2] < 130)
        colored = np.mean((center[:, :, 1] > 80) & (center[:, :, 2] > 125))
        if dark < .03 or colored > .08:
            continue
        point = (x + bw // 2, top + y + bh // 2)
        candidates.append((fill - abs(point[1] - expected_y) / w, point))
    # The like buttons are the lowest aligned row above Drops. Bright avatar
    # details and names higher up must not replace that row when its UI shifts.
    groups = []
    for _, point in candidates:
        group = [item for item in candidates if abs(item[1][1] - point[1]) < .018 * h]
        groups.append(group)
    if not groups:
        return []
    row = max(groups, key=lambda g: (len(g) >= 2, np.mean([p[1] for _, p in g])))
    return sorted(p for _, p in sorted(row, reverse=True)[:4])


def remember_like_patches(image, points, evidence):
    """Keep the actual white-button areas seen before sending outgoing likes."""
    full = np.asarray(image.convert("RGB"))
    frame, _ = game_frame(full)
    width = frame.shape[1] if frame is not None else min(full.shape[1], full.shape[0])
    dx, dy = max(4, round(.045 * width)), max(4, round(.027 * width))
    for point in points:
        if point in evidence:
            continue
        x, y = point
        box = (max(0, x-dx), max(0, y-dy), min(full.shape[1], x+dx), min(full.shape[0], y+dy))
        x1, y1, x2, y2 = box
        patch = full[y1:y2, x1:x2].copy()
        if patch.size:
            evidence[point] = (box, patch)


def clicked_likes_cleared(image, evidence, clicked):
    """Each successfully clicked white button must disappear from its own area.

    Incoming gold indicators are never counted as sent likes or as completion.
    A detector returning zero is insufficient if the original white pills remain.
    """
    if not clicked or any(p not in evidence for p in clicked):
        return False
    full = np.asarray(image.convert("RGB"))
    for point in clicked:
        (x1, y1, x2, y2), before = evidence[point]
        after = full[y1:y2, x1:x2]
        if before.shape != after.shape or not after.size:
            return False
        original = cv2.cvtColor(before, cv2.COLOR_RGB2HSV)
        current = cv2.cvtColor(after, cv2.COLOR_RGB2HSV)
        old_white = np.mean((original[:, :, 1] < 95) & (original[:, :, 2] > 125))
        new_white = np.mean((current[:, :, 1] < 95) & (current[:, :, 2] > 125))
        changed = np.abs(before.astype(np.int16) - after.astype(np.int16)).mean()
        if old_white < .2 or new_white > old_white * .45 or changed < 18:
            return False
    return True


def rank_banner(frame):
    h = frame.shape[0]
    hsv = cv2.cvtColor(frame[int(.10 * h):int(.36 * h)], cv2.COLOR_RGB2HSV)
    yellow = ((hsv[:, :, 0] > 18) & (hsv[:, :, 0] < 48)
              & (hsv[:, :, 1] > 55) & (hsv[:, :, 1] < 220) & (hsv[:, :, 2] > 140))
    rows = np.mean(yellow, axis=1) > .60
    edges = np.diff(np.r_[False, rows, False].astype(int))
    return any(b - a >= .025 * h for a, b in
               zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def results_fast(frame):
    """Rank banner + Drops divider identify results even if thumbs are missed."""
    h, w = frame.shape[:2]
    top, bottom = int(.55 * h), int(.84 * h)
    hsv = cv2.cvtColor(frame[top:bottom], cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 1] < 70) & (hsv[:, :, 2] > 100)).astype(np.uint8) * 255
    lines = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, max(1, int(.65 * w))), np.uint8))
    contours, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    banner = rank_banner(frame)
    for contour in contours:
        _, y, bw, bh = cv2.boundingRect(contour)
        if bw < .7 * w or bh > .008 * h:
            continue
        if banner:
            return results_layout(frame, top + y)
        # Gold Random reward badges on the queue/menu resemble received-like
        # pills. Only actual white controls can substitute for the rank banner.
        if len(find_like_icons(frame, top + y)) >= 2:
            return results_layout(frame, top + y)
    return None

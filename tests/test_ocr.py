"""Exercise the real packaged models, not an injected OCR stub."""
import os
from pathlib import Path
import unittest

from PIL import Image, ImageDraw, ImageFont

from autoqueue.vision import Recognizer


class OCRIntegrationTests(unittest.TestCase):
    def test_real_models_read_text_buttons_without_reference_images(self):
        fonts = [Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/arial.ttf',
                 Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
        font_path = next((p for p in fonts if p.exists()), None)
        if font_path is None:
            self.skipTest('No supported system font available for generated fixtures')
        recognizer = Recognizer()
        model = recognizer.reader
        calls = []
        def counted_reader(*args, **kwargs):
            calls.append(1)
            return model(*args, **kwargs)
        recognizer.reader = counted_reader
        for state in ('menu', 'accept', 'queue', 'world'):
            with self.subTest(state=state):
                image = Image.new('RGB', (600, 1100), (28, 53, 48))
                draw = ImageDraw.Draw(image)
                def label(value, xy, size=26, fill='white'):
                    draw.text(xy, value, font=ImageFont.truetype(str(font_path), size), fill=fill)
                if state == 'world':
                    label('Demonseal Gorge', (430, 260), 15)
                    label('Explore', (420, 1050), 20)
                else:
                    label('Demonseal Gorge - Hard', (50, 70), 28)
                    draw.rounded_rectangle((310, 930, 575, 995), radius=24, fill=(205, 216, 75))
                    if state == 'accept':
                        label('Decline', (100, 950))
                        label('Accept', (400, 950), fill='black')
                    else:
                        label('Team 2/4', (90, 940))
                        label('Cancel' if state == 'queue' else 'Match', (400, 950), fill='black')
                previous_calls = len(calls)
                view = recognizer.inspect(image)
                self.assertEqual(len(calls), previous_calls + 1)
                self.assertEqual(view.state, state)
                if state in ('menu', 'accept'):
                    x, y = view.targets['match' if state == 'menu' else 'accept']
                    self.assertTrue(310 < x < 575 and 930 < y < 995)
                # Fresh screenshots with unchanged UI labels should validate
                # the automatic anchors, without repeating model inference.
                for _ in range(10):
                    fresh = recognizer.inspect(image.copy())
                    self.assertEqual(fresh.state, state)
                self.assertEqual(len(calls), previous_calls + 1)


if __name__ == '__main__':
    unittest.main()

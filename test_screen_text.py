import unittest

from screen_text import blocks_from_rows, choose_nearest, read_blocks, sentence_spans


def row(text, x=20, y=20, width=220, height=20, confidence=.95):
    return [[[x, y], [x + width, y], [x + width, y + height], [x, y + height]], text, confidence]


class ScreenTextTests(unittest.TestCase):
    def texts(self, rows, language='en'):
        return [block['text'] for block in blocks_from_rows(rows, language)]

    def test_wraps_to_complete_sentences(self):
        blocks = blocks_from_rows([row('We should leave before the'),
                                   row('rain starts. Bring an umbrella.', y=48)])
        self.assertEqual([b['text'] for b in blocks],
                         ['We should leave before the rain starts.', 'Bring an umbrella.'])
        self.assertEqual(len(blocks[0]['boxes']), 2)
        self.assertGreater(blocks[1]['box'][0], 20)

    def test_columns_do_not_merge(self):
        rows = [row('Left column starts', x=20), row('Right column starts', x=360),
                row('and continues.', x=20, y=48), row('and ends here.', x=360, y=48)]
        self.assertEqual(self.texts(rows), ['Left column starts and continues.',
                                           'Right column starts and ends here.'])

    def test_large_gaps_separate_paragraphs(self):
        self.assertEqual(self.texts([row('Settings'), row('Open the account.', y=150)]),
                         ['Settings', 'Open the account.'])

    def test_word_fragments_on_same_line(self):
        rows = [row('Bring', width=45), row('your umbrella.', x=72, width=150)]
        self.assertEqual(self.texts(rows), ['Bring your umbrella.'])

    def test_hyphenated_wrap(self):
        rows = [row('This is an inter-'), row('national meeting.', y=48)]
        self.assertEqual(self.texts(rows), ['This is an international meeting.'])

    def test_chinese_spacing_and_wrap(self):
        rows = [row('我们 应该在下雨前'), row('离开。请带上伞！', y=48)]
        self.assertEqual(self.texts(rows, 'zh'), ['我们应该在下雨前离开。', '请带上伞！'])

    def test_source_language_filter_on_bilingual_screen(self):
        rows = [row('Bring your umbrella.'), row('请带上雨伞。', y=48)]
        self.assertEqual(self.texts(rows, 'en'), ['Bring your umbrella.'])
        self.assertEqual(self.texts(rows, 'zh'), ['请带上雨伞。'])

    def test_parallel_translation_in_one_row(self):
        rows = [row('Hello world | 你好世界')]
        english, chinese = blocks_from_rows(rows, 'en'), blocks_from_rows(rows, 'zh')
        self.assertEqual(english[0]['text'], 'Hello world')
        self.assertEqual(chinese[0]['text'], '你好世界')
        self.assertLess(english[0]['box'][2], chinese[0]['box'][0])

    def test_chinese_sentence_keeps_english_product_name(self):
        self.assertEqual(self.texts([row('请打开 Settings 并保存。')], 'zh'),
                         ['请打开 Settings 并保存。'])

    def test_abbreviations_initials_and_decimal(self):
        text = 'Dr. Smith met Mr. A. Brown at 3.5 miles. Bring it here!'
        self.assertEqual([text[a:b] for a, b in sentence_spans(text)],
                         ['Dr. Smith met Mr. A. Brown at 3.5 miles.', 'Bring it here!'])

    def test_abbreviation_at_wrap_does_not_end_sentence(self):
        self.assertEqual(self.texts([row('Please ask Dr.'), row('Smith for help.', y=48)]),
                         ['Please ask Dr. Smith for help.'])

    def test_completed_lines_stay_separate(self):
        self.assertEqual(self.texts([row('First sentence.'), row('Second sentence.', y=48)]),
                         ['First sentence.', 'Second sentence.'])

    def test_closest_sentence_inside_one_ocr_line(self):
        blocks = blocks_from_rows([row('First sentence. Second sentence.', width=360)])
        self.assertEqual(choose_nearest(blocks, (330, 30))['text'], 'Second sentence.')
        self.assertIsNone(choose_nearest(blocks, (800, 500)))

    def test_wrapped_sentence_uses_fragments_not_enclosing_area(self):
        block = {'text': 'wrapped', 'box': (0, 0, 400, 100),
                 'boxes': [(0, 0, 400, 20), (0, 80, 40, 100)]}
        other = {'text': 'nearby', 'box': (250, 85, 300, 105)}
        self.assertIs(choose_nearest([block, other], (280, 95)), other)

    def test_low_confidence_and_malformed_rows(self):
        rows = [None, [[], 'broken', .9], row('noise', confidence=.2),
                row('bad', confidence=float('nan')), row('Recognized sentence.')]
        self.assertEqual(self.texts(rows), ['Recognized sentence.'])

    def test_scaled_coordinates_return_to_original_image(self):
        blocks = blocks_from_rows([row('Recognized sentence.', x=40, y=40, width=440, height=40)],
                                  'en', scale_x=2, scale_y=2)
        self.assertEqual(blocks[0]['box'], (20., 20., 240., 40.))

    def test_read_blocks_bounded_resize_and_geometry(self):
        from PIL import Image
        calls = []

        def ocr(image, **kwargs):
            calls.append((image.shape, kwargs))
            return [row('Bring an umbrella.', x=40, y=40, width=400, height=40)], []

        blocks = read_blocks(ocr, Image.new('RGB', (500, 200)), 'en')
        self.assertEqual(calls[0][0], (400, 1000, 3))
        self.assertEqual(blocks[0]['box'], (20., 20., 220., 40.))
        read_blocks(ocr, Image.new('RGB', (3840, 2160)), 'en')
        self.assertEqual(calls[1][0][1], 2000)
        self.assertEqual(len(calls), 2)  # Never retry every frame with expensive OCR passes.


if __name__ == '__main__':
    unittest.main()

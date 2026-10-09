"""Exercise lookup data, rapid selection, cache sharing and Tk lifetime safety."""
import threading
import time
import tkinter as tk
import unittest
import gc
from unittest.mock import patch

import embedded_dictionary as dictionary
from dictionary_ui import DictionaryWindow
from runtime_paths import BUNDLE_ROOT

has_dictionary=unittest.skipUnless((BUNDLE_ROOT/'dictionary/ecdict.sqlite3').is_file(), 'Optional ECDICT dataset: run tools/prepare_dictionary.py')


class DictionaryPanelTests(unittest.TestCase):
    def setUp(self):
        dictionary.clear_lookup_cache()
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.saved = []
        self.panel = dictionary.DictionaryPanel(self.root, self.saved.append)
        self.panel.frame.pack(fill='both', expand=True)

    def tearDown(self):
        self.root.destroy()
        self.assertEqual(self.errors, [])
        # Each case creates its own Tcl interpreter. Release destroyed widget
        # cycles on its owner thread before another lookup worker starts.
        self.panel = None
        self.root = None
        gc.collect()

    def pump(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return
            time.sleep(.01)
        self.fail('Timed out waiting for dictionary lookup')

    def text(self):
        return self.panel.output.get('1.0', 'end')

    @has_dictionary
    def test_real_lookup_save_name_and_theme(self):
        self.panel.show_query('rain', 'We should leave before the rain.')
        self.pump(lambda: not self.panel.busy)
        self.assertIn('雨', self.text())
        self.panel.name_button.invoke()
        self.assertEqual(self.saved, ['rain'])
        self.panel.apply_theme({'card': '#fff8ee', 'accent': '#a53347'})
        self.assertEqual(self.panel.output.cget('bg'), '#fff8ee')
        self.assertEqual(self.panel.button.cget('bg'), '#a53347')
        self.assertIsNone(self.panel._after_id, 'Idle dictionary should not keep polling')

    @has_dictionary
    def test_unknown_names_and_long_inputs_keep_real_dictionary_messages(self):
        self.panel.show_query('zxqnotarealpersonxyz')
        self.pump(lambda: not self.panel.busy)
        self.assertIn('未收录', self.text())
        self.panel.show_query('one two three four five six seven')
        self.pump(lambda: not self.panel.busy)
        self.assertIn('最多 6', self.text())

    def test_rapid_queries_show_only_latest_and_drop_intermediate(self):
        started = threading.Event()
        release = threading.Event()
        seen = []

        def fake(query):
            seen.append(query)
            if query == 'old':
                started.set()
                release.wait(3)
            return 'RESULT:' + query

        with patch.object(dictionary, 'cached_lookup', side_effect=fake):
            self.panel.show_query('old')
            self.assertTrue(started.wait(2))
            self.panel.show_query('middle')
            self.panel.show_query('latest', '最新上下文 ' * 80)
            release.set()
            self.pump(lambda: not self.panel.busy)
        self.assertEqual(seen, ['old', 'latest'])
        self.assertIn('RESULT:latest', self.text())
        self.assertNotIn('RESULT:old', self.text())
        self.assertEqual(self.panel.query.get(), 'latest')
        self.assertLessEqual(len(self.panel.context.get().splitlines()), 2)
        self.assertIn('…', self.panel.context.get())

    @has_dictionary
    def test_popup_and_embedded_use_one_lookup_for_same_word(self):
        original = dictionary.lookup
        with patch.object(dictionary, 'lookup', wraps=original) as lookup:
            window = DictionaryWindow(self.root, self.saved.append)
            window.win.withdraw()
            self.panel.show_query('Rain')
            window.show(' rain ', 'A rainy afternoon.')
            window.win.withdraw()
            self.pump(lambda: not self.panel.busy and not window.busy)
            self.assertEqual(lookup.call_count, 1)
            self.assertIn('雨', window.output.get('1.0', 'end'))
            window.apply_theme({'card': '#fffcf6'})
            self.assertEqual(window.output.cget('bg'), '#fffcf6')
            window.close()
            self.assertTrue(window.closed)

    def test_close_during_lookup_cancels_timer_and_worker_never_touches_tk(self):
        started = threading.Event()
        release = threading.Event()
        completed = threading.Event()

        def delayed(_query):
            started.set()
            release.wait(3)
            completed.set()
            return 'finished after close'

        with patch.object(dictionary, 'cached_lookup', side_effect=delayed):
            self.panel.show_query('rain')
            self.assertTrue(started.wait(2))
            self.panel.show_query('pending')
            self.panel.close()
            self.assertIsNone(self.panel._after_id)
            self.assertIsNone(self.panel.pending)
            release.set()
            self.assertTrue(completed.wait(2))
            self.root.update()
            self.panel.show_query('closed')
        self.assertTrue(self.panel.closed)

    def test_parent_destroy_disposes_panel_without_explicit_close(self):
        holder = tk.Frame(self.root)
        panel = dictionary.DictionaryPanel(holder, self.saved.append)
        panel.show_query('rain')
        holder.destroy()
        self.assertTrue(panel.closed)
        self.assertIsNone(panel._after_id)


if __name__ == '__main__':
    unittest.main()

"""Static integration guards for optional homepage motion.

Browser QA also verifies movement, the repeat boundary, interaction and mobile sizing.
"""
import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HomeMotionTests(unittest.TestCase):
    def setUp(self):
        self.script = (ROOT / 'assets/home-motion.js').read_text(encoding="utf-8")
        self.css = (ROOT / 'assets/home-motion.css').read_text(encoding="utf-8")

    def test_shared_pages_load_motion_once(self):
        for name in ['index.html', 'browse/index.html', 'news/index.html',
                     'first-nations/mistawasis-nehiyawak/index.html']:
            with self.subTest(page=name):
                page = (ROOT / name).read_text(encoding="utf-8")
                self.assertEqual(len(re.findall(r'/assets/home-motion\.js\?v=[^\"]+', page)), 1)
                self.assertEqual(len(re.findall(r'/assets/home-motion\.css\?v=[^\"]+', page)), 1)

    def test_assets_exist(self):
        for name in ['hero-snowflake.svg', 'hero-feathers.webp', 'motion-pause.svg', 'motion-play.svg',
                     'motion-icons-LICENSE']:
            self.assertTrue((ROOT / 'assets' / name).is_file())

    def test_decorative_artwork_is_noninteractive(self):
        self.assertIn("layer.setAttribute('aria-hidden', 'true')", self.script)
        self.assertIn("artwork.alt = ''", self.script)
        self.assertIn('pointer-events:none', self.css)

    def test_reduced_motion_changes_are_supported(self):
        self.assertIn("matchMedia('(prefers-reduced-motion: reduce)')", self.script)
        self.assertIn("reducedMotion.addEventListener('change', sizeLoop)", self.script)
        self.assertIn('@media(prefers-reduced-motion:reduce)', self.css)
        self.assertIn('.hero-particle,.hero-particle img{animation:none}', self.css)

    def test_duplicate_cards_are_not_repeated_to_screen_readers(self):
        self.assertIn("clone.setAttribute('aria-hidden', 'true')", self.script)
        self.assertIn('node.tabIndex = -1', self.script)
        self.assertIn("node.removeAttribute('id')", self.script)
        self.assertIn("group.querySelectorAll('.recent-btn')[index]?.click()", self.script)

    def test_animation_pauses_for_interaction_and_hidden_pages(self):
        for event in ['pointerenter', 'pointerdown', 'focusin', 'focusout', 'visibilitychange']:
            self.assertIn(f"addEventListener('{event}'", self.script)
        self.assertIn('!document.hidden', self.script)
        self.assertIn("button.setAttribute('aria-pressed'", self.script)

    def test_loop_uses_elapsed_time_and_exact_group_width(self):
        self.assertIn('group.getBoundingClientRect().width', self.script)
        self.assertIn('Math.min(time - previousTime, 64)', self.script)
        self.assertIn('(position + elapsed * .028) % period', self.script)
        self.assertIn('Math.ceil(list.clientWidth / period) + 1', self.script)
        self.assertIn('gap:8px;padding:4px', self.css)

    def test_mobile_controls_are_focus_reveal_only_and_touch_does_not_latch_pause(self):
        self.assertIn('clip-path:inset(50%)', self.css)
        self.assertIn('.motion-toggle:focus-visible{width:44px', self.css)
        self.assertIn('grid-template-columns:minmax(0,1fr);position:relative', self.css)
        self.assertNotIn('control.setPaused(true)', self.script)
        self.assertIn("window.addEventListener('pointerup', releasePointer)", self.script)
        self.assertIn("window.addEventListener('pointercancel', releasePointer)", self.script)

    def test_runtime_touch_keyboard_and_motion_preferences(self):
        import shutil, subprocess
        node=shutil.which('node')
        if not node:self.skipTest('Node.js required for motion interaction tests')
        result=subprocess.run([node,'tests/test_home_motion_runtime.js'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_no_extra_data_requests_or_financial_logic(self):
        for fragment in ['fetch(', 'localStorage', 'capitalData', 'bandsData']:
            self.assertNotIn(fragment, self.script)


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""userboxmaker の unittest。ネットワークには出ず、テストクライアントで確認する。"""

import html
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module  # noqa: E402


def extract_out(page_html, element_id):
    """出力用 textarea の中身を取り出して HTML エンティティを戻す。"""
    m = re.search(
        r'<textarea[^>]*id="%s"[^>]*>(.*?)</textarea>' % element_id,
        page_html,
        re.DOTALL,
    )
    if not m:
        raise AssertionError("textarea #%s not found" % element_id)
    return html.unescape(m.group(1))


VALID = {
    "id_text": "Test",
    "info_text": "これはテストです。",
    "id_c": "#112233",
    "id_fc": "#ffffff",
    "info_c": "#eeeeee",
    "info_fc": "#000000",
    "border_c": "#445566",
}


class UserboxMakerTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_healthz(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})

    def test_index_ok(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ユーザーボックスメーカー", resp.get_data(as_text=True))

    def test_generate_contains_userbox_and_values(self):
        resp = self.client.post("/", data=VALID)
        self.assertEqual(resp.status_code, 200)
        out = extract_out(resp.get_data(as_text=True), "out-wikitext")
        self.assertIn("{{Userbox", out)
        self.assertIn("Test", out)
        self.assertIn("これはテストです。", out)
        self.assertIn("#112233", out)
        self.assertIn("#445566", out)

    def test_template_version_has_noinclude(self):
        resp = self.client.post("/", data=VALID)
        out = extract_out(resp.get_data(as_text=True), "out-template")
        self.assertIn("{{Userbox", out)
        self.assertIn("<noinclude>", out)
        self.assertIn("</noinclude>", out)
        self.assertIn("[[Category:", out)

    def test_escape_pipe_and_braces(self):
        data = dict(VALID)
        data["info_text"] = "a|b {{c}}"
        resp = self.client.post("/", data=data)
        self.assertEqual(resp.status_code, 200)
        out = extract_out(resp.get_data(as_text=True), "out-wikitext")
        # 縦棒は {{!}} に、波括弧は数値文字参照になっていること
        self.assertIn("a{{!}}b", out)
        self.assertNotIn("a|b", out)
        self.assertIn("&#123;", out)
        # 出力中の {{ は {{Userbox と {{!}} の分だけ
        self.assertEqual(out.count("{{"), 1 + out.count("{{!}}"))

    def test_escape_in_unit(self):
        self.assertEqual(app_module.escape_wikitext("x|y"), "x{{!}}y")
        self.assertNotIn("{{", app_module.escape_wikitext("{{x}}").replace("{{!}}", ""))
        self.assertEqual(app_module.escape_wikitext("a\nb"), "a b")

    def test_invalid_colors_do_not_500(self):
        data = dict(VALID)
        data.update(
            {"id_c": "not-a-color", "info_c": "#zzz", "border_c": "", "id_fc": "red"}
        )
        resp = self.client.post("/", data=data)
        self.assertEqual(resp.status_code, 200)
        out = extract_out(resp.get_data(as_text=True), "out-wikitext")
        # 不正な色は既定値に倒れていること
        self.assertIn(app_module.DEFAULTS["id_c"], out)
        self.assertNotIn("not-a-color", out)

    def test_color_normalize_short_hex(self):
        self.assertEqual(app_module.normalize_color("#ABC", "#000000"), "#aabbcc")
        self.assertEqual(app_module.normalize_color("#A1B2C3", "#000000"), "#a1b2c3")
        self.assertEqual(app_module.normalize_color("blue", "#000000"), "#000000")

    def test_preset_loads(self):
        resp = self.client.get("/?preset=0")
        self.assertEqual(resp.status_code, 200)
        page = resp.get_data(as_text=True)
        self.assertIn("日本語版ウィキペディアに参加しています", page)
        out = extract_out(page, "out-wikitext")
        self.assertIn("{{Userbox", out)

    def test_scheme_loads(self):
        resp = self.client.get("/?scheme=dark")
        self.assertEqual(resp.status_code, 200)
        out = extract_out(resp.get_data(as_text=True), "out-wikitext")
        self.assertIn("#333333", out)

    def test_bad_preset_and_scheme_do_not_500(self):
        for url in ("/?preset=99", "/?preset=abc", "/?scheme=nope"):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)


if __name__ == "__main__":
    unittest.main()

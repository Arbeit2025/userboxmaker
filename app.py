# -*- coding: utf-8 -*-
"""
userboxmaker（ユーザーボックスメーカー）

Wikipedia の利用者ページで使う「ユーザーボックス」を作るための、
単一ファイル Flask の Web 生成ツールです。

フォームに左側の短い文字と右側の本文、色を入力すると、
  - ユーザーボックス風のプレビュー（HTML）
  - {{Userbox}} を使ったウィキテキスト（そのまま貼れる版）
  - テンプレートページ用の版（<noinclude> の説明・カテゴリ付き）
を表示します。生成はこのページの中だけで完結し、Wikipedia への投稿は
行いません。Bot 承認は不要な Web 生成ツールです（Bot ではありません）。
データベースは使いません。入力値は保存されません。

目次
  1. 設定・定数（既定値、カラープリセット、入力例プリセット）
  2. 色の正規化
  3. ウィキテキストのエスケープ
  4. ウィキテキスト生成（通常版／テンプレート版）
  5. 入力値の収集
  6. ページ表示（HTML テンプレート）
  7. ルート
  8. 起動
"""

import re

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# ============================
# 1. 設定・定数
# ============================

DEFAULTS = {
    "id_text": "Wiki",
    "info_text": "この利用者は日本語版ウィキペディアに参加しています。",
    "id_c": "#d6e9f8",
    "id_fc": "#1a1a1a",
    "info_c": "#f2f8fd",
    "info_fc": "#1a1a1a",
    "border_c": "#7aa7c7",
}

COLOR_KEYS = ["id_c", "id_fc", "info_c", "info_fc", "border_c"]
MAX_ID_LEN = 40
MAX_INFO_LEN = 500

# カラープリセット8種（キー: 表示名と5色）
SCHEMES = {
    "blue": {
        "label": "あお",
        "colors": {
            "id_c": "#d6e9f8", "id_fc": "#14425f",
            "info_c": "#f2f8fd", "info_fc": "#1a1a1a",
            "border_c": "#7aa7c7",
        },
    },
    "green": {
        "label": "みどり",
        "colors": {
            "id_c": "#d9ead3", "id_fc": "#274e13",
            "info_c": "#f4f9f1", "info_fc": "#1a1a1a",
            "border_c": "#6aa84f",
        },
    },
    "red": {
        "label": "あか",
        "colors": {
            "id_c": "#f8d6dc", "id_fc": "#6e1423",
            "info_c": "#fdf2f4", "info_fc": "#1a1a1a",
            "border_c": "#c76a7a",
        },
    },
    "purple": {
        "label": "むらさき",
        "colors": {
            "id_c": "#e3d6f8", "id_fc": "#3d1a6e",
            "info_c": "#f7f2fd", "info_fc": "#1a1a1a",
            "border_c": "#9673c7",
        },
    },
    "orange": {
        "label": "オレンジ",
        "colors": {
            "id_c": "#fbe3c2", "id_fc": "#7a3d00",
            "info_c": "#fdf6ec", "info_fc": "#1a1a1a",
            "border_c": "#e09a3e",
        },
    },
    "sakura": {
        "label": "さくら",
        "colors": {
            "id_c": "#fadce8", "id_fc": "#7c2145",
            "info_c": "#fdf3f7", "info_fc": "#1a1a1a",
            "border_c": "#e08bb0",
        },
    },
    "gray": {
        "label": "グレー",
        "colors": {
            "id_c": "#e0e0e0", "id_fc": "#333333",
            "info_c": "#f7f7f7", "info_fc": "#1a1a1a",
            "border_c": "#999999",
        },
    },
    "dark": {
        "label": "くろ",
        "colors": {
            "id_c": "#333333", "id_fc": "#ffffff",
            "info_c": "#555555", "info_fc": "#ffffff",
            "border_c": "#111111",
        },
    },
}

# 入力例プリセット3種
PRESETS = [
    {
        "label": "日本語版に参加",
        "id_text": "Wiki",
        "info_text": "この利用者は日本語版ウィキペディアに参加しています。",
        "scheme": "blue",
    },
    {
        "label": "Python使い",
        "id_text": "Py",
        "info_text": "この利用者はPythonでプログラムを書いています。",
        "scheme": "green",
    },
    {
        "label": "お茶が好き",
        "id_text": "茶",
        "info_text": "この利用者はお茶が好きです。",
        "scheme": "sakura",
    },
]

# ============================
# 2. 色の正規化
# ============================

_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def normalize_color(value, default):
    """#RRGGBB / #RGB の16進数カラーだけを受け付け、それ以外は既定値に倒す。"""
    if not isinstance(value, str):
        return default
    value = value.strip()
    if not _COLOR_RE.match(value):
        return default
    value = value.lower()
    if len(value) == 4:  # #RGB -> #RRGGBB
        value = "#" + "".join(ch * 2 for ch in value[1:])
    return value


# ============================
# 3. ウィキテキストのエスケープ
# ============================


def escape_wikitext(text):
    """テンプレート引数の中で壊れる文字を安全な表記に置き換える。"""
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    # 括弧は数値文字参照にして、テンプレート呼び出しとして解釈させない
    text = text.replace("{", "&#123;").replace("}", "&#125;")
    # 縦棒は {{!}} に（上の置換のあとで行うので {{!}} 自体は壊れない）
    text = text.replace("|", "{{!}}")
    # リンクになりうる角括弧と、タグになりうる山括弧も無害化する
    text = text.replace("[", "&#91;").replace("]", "&#93;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return text.strip()


# ============================
# 4. ウィキテキスト生成
# ============================


def build_wikitext(values):
    """{{Userbox}} を使った通常版ウィキテキスト。"""
    lines = [
        "{{Userbox",
        " | border-c = %s" % values["border_c"],
        " | id = %s" % escape_wikitext(values["id_text"]),
        " | id-c = %s" % values["id_c"],
        " | id-fc = %s" % values["id_fc"],
        " | info = %s" % escape_wikitext(values["info_text"]),
        " | info-c = %s" % values["info_c"],
        " | info-fc = %s" % values["info_fc"],
        "}}",
    ]
    return "\n".join(lines)


def build_template_wikitext(values):
    """テンプレートページ用の版（<noinclude> で説明とカテゴリ付き）。"""
    doc = (
        "<noinclude>\n"
        "== 使い方 ==\n"
        "このテンプレートは、利用者ページに貼り付けて使うユーザーボックスです。\n"
        "テンプレートページ（Template:名前）にこのコードを貼ると、"
        "利用者ページからは {{名前}} の形で呼び出せます。\n"
        "色や文言を変えたいときは、このページの {{Userbox}} の引数を編集してください。\n"
        "[[Category:ユーザーボックス]]\n"
        "</noinclude>"
    )
    return build_wikitext(values) + "\n" + doc


# ============================
# 5. 入力値の収集
# ============================


def collect_values():
    """GET のクエリ／POST のフォームから入力値を集め、正規化して返す。"""
    values = dict(DEFAULTS)
    source = request.form if request.method == "POST" else request.args

    scheme_key = source.get("scheme", "")
    if scheme_key in SCHEMES:
        values.update(SCHEMES[scheme_key]["colors"])

    preset_index = source.get("preset", "")
    if preset_index != "":
        try:
            idx = int(preset_index)
        except (TypeError, ValueError):
            idx = -1
        if 0 <= idx < len(PRESETS):
            preset = PRESETS[idx]
            values["id_text"] = preset["id_text"]
            values["info_text"] = preset["info_text"]
            values.update(SCHEMES[preset["scheme"]]["colors"])

    for key in DEFAULTS:
        raw = source.get(key)
        if raw is not None and str(raw).strip() != "":
            values[key] = str(raw)

    values["id_text"] = values["id_text"].strip()[:MAX_ID_LEN] or DEFAULTS["id_text"]
    values["info_text"] = (
        values["info_text"].strip()[:MAX_INFO_LEN] or DEFAULTS["info_text"]
    )
    for key in COLOR_KEYS:
        values[key] = normalize_color(values[key], DEFAULTS[key])
    return values


# ============================
# 6. ページ表示（HTML テンプレート）
# ============================

INDEX_HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ユーザーボックスメーカー | userboxmaker</title>
<style>
body { font-family: sans-serif; margin: 2em auto; max-width: 760px; padding: 0 1em; color: #222; }
h1 { font-size: 1.4em; }
label { display: block; margin-top: .8em; font-weight: bold; }
input[type="text"], textarea { width: 100%; box-sizing: border-box; padding: .4em; }
.colors { display: flex; flex-wrap: wrap; gap: 1em; }
.colors label { font-weight: normal; }
input[type="color"] { width: 64px; height: 36px; padding: 0; border: 1px solid #ccc; background: none; }
button { margin-top: 1em; padding: .5em 1.4em; font-size: 1em; cursor: pointer; }
a.btn { display: inline-block; margin: .2em .2em .2em 0; padding: .25em .7em; border: 1px solid #999; border-radius: 999px; color: #225; text-decoration: none; font-size: .9em; background: #f4f6f8; }
textarea.out { width: 100%; box-sizing: border-box; font-family: monospace; padding: .5em; }
.copy { margin-top: .3em; padding: .3em 1em; }
.ub { display: flex; width: 270px; max-width: 100%; border: 1px solid; margin: .5em 0; font-size: 90%; line-height: 1.4; }
.ub-id { flex: 0 0 46px; display: flex; align-items: center; justify-content: center; text-align: center; font-weight: bold; font-size: 110%; padding: 6px 2px; word-break: break-all; }
.ub-info { flex: 1; padding: 6px 8px; }
.note { color: #555; font-size: .9em; }
</style>
</head>
<body>
<h1>ユーザーボックスメーカー</h1>
<p>Wikipedia の利用者ページで使うユーザーボックスのウィキテキストを生成します。
生成はこのページの中だけで行われ、Wikipedia への投稿はしません（Bot ではなく Web 生成ツールなので、Bot 承認は不要です）。</p>

<p>入力例プリセット：
{% for p in presets %}<a class="btn" href="/?preset={{ loop.index0 }}">{{ p.label | e }}</a>{% endfor %}
</p>
<p>カラープリセット：
{% for key, s in schemes.items() %}<a class="btn" href="/?scheme={{ key }}">{{ s.label | e }}</a>{% endfor %}
</p>

<form method="post" action="/">
  <label for="id_text">左側の短い文字（例：Wiki）</label>
  <input type="text" id="id_text" name="id_text" maxlength="40" value="{{ values.id_text | e }}">
  <label for="info_text">右側の本文</label>
  <textarea id="info_text" name="info_text" rows="3" maxlength="500">{{ values.info_text | e }}</textarea>
  <div class="colors">
    <label>左の背景色<br><input type="color" name="id_c" value="{{ values.id_c | e }}"></label>
    <label>左の文字色<br><input type="color" name="id_fc" value="{{ values.id_fc | e }}"></label>
    <label>右の背景色<br><input type="color" name="info_c" value="{{ values.info_c | e }}"></label>
    <label>右の文字色<br><input type="color" name="info_fc" value="{{ values.info_fc | e }}"></label>
    <label>枠の色<br><input type="color" name="border_c" value="{{ values.border_c | e }}"></label>
  </div>
  <button type="submit">生成する</button>
</form>

<h2>プレビュー</h2>
<div class="ub" style="border-color: {{ values.border_c | e }};">
  <div class="ub-id" style="background: {{ values.id_c | e }}; color: {{ values.id_fc | e }};">{{ values.id_text | e }}</div>
  <div class="ub-info" style="background: {{ values.info_c | e }}; color: {{ values.info_fc | e }};">{{ values.info_text | e }}</div>
</div>

<h2>ウィキテキスト（そのまま貼れる版）</h2>
<textarea class="out" id="out-wikitext" rows="10" readonly>{{ wikitext | e }}</textarea>
<button type="button" class="copy" onclick="copyOut('out-wikitext')">コピーする</button>
<p class="note">利用者ページの編集画面に貼り付けて使います。</p>

<h2>ウィキテキスト（テンプレートページ用）</h2>
<textarea class="out" id="out-template" rows="14" readonly>{{ template_wikitext | e }}</textarea>
<button type="button" class="copy" onclick="copyOut('out-template')">コピーする</button>
<p class="note">「Template:好きな名前」というページを作って貼ると、利用者ページから {{ "{{名前}}" }} の形で呼び出せるようになります。説明とカテゴリは &lt;noinclude&gt; の中にあるので、呼び出し先にはボックスだけが表示されます。</p>

<script>
function copyOut(id) {
  var t = document.getElementById(id);
  t.select();
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(t.value);
  } else {
    document.execCommand('copy');
  }
}
</script>
</body>
</html>
"""

# ============================
# 7. ルート
# ============================


@app.route("/", methods=["GET", "POST"])
def index():
    values = collect_values()
    return render_template_string(
        INDEX_HTML,
        values=values,
        wikitext=build_wikitext(values),
        template_wikitext=build_template_wikitext(values),
        schemes=SCHEMES,
        presets=PRESETS,
    )


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"})


# ============================
# 8. 起動
# ============================

if __name__ == "__main__":
    import os

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))

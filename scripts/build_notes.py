#!/usr/bin/env python3
"""Build the notes section from markdown notes in the obsidian_public repo.

Usage:
  python scripts/build_notes.py                 # clone https://github.com/Zoe-Choi/obsidian_public into a temp dir
  python scripts/build_notes.py --src <dir>     # use an existing checkout instead of cloning

Rules:
  - Only notes whose frontmatter has `publish: true` are built. Everything else is ignored.
  - Category: `카테고리:` (one of CATEGORY_ORDER) wins; otherwise mapped from the `분류:` prefix.
  - Only `개념/*.md` and `문서/개발/*.md` are scanned.
  - The build aborts if any publishable note matches the secret patterns below
    (IP addresses, internal hostnames, credentials). Fix the note, then rebuild.
Outputs:
  notes/index.html, notes/<slug>.html, and the teaser block in index.html
  between <!-- notes:teaser:start --> and <!-- notes:teaser:end -->.
"""
import argparse, datetime, glob, html, io, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_URL = 'https://github.com/Zoe-Choi/obsidian_public.git'
SOURCES = [('개념', '개념'), (os.path.join('문서', '개발'), '가이드')]

# category by `분류` prefix; first match wins, else '기타'
CATEGORY_RULES = [
    ('Spark / YARN', 'Spark · YARN'),
    ('Spark / Trino / Airflow', 'Spark · YARN'),
    ('Spark / Iceberg', 'Iceberg · Lakehouse'),
    ('Lakehouse', 'Iceberg · Lakehouse'),
    ('Spark / Trino / Iceberg', 'Iceberg · Lakehouse'),
    ('모니터링', '운영 · 모니터링'),
    ('Python', 'Python · DB'),
    ('개발', '저장소 · 인프라'),
    ('work', '저장소 · 인프라'),
]
CATEGORY_ORDER = ['Spark · YARN', 'Iceberg · Lakehouse', '저장소 · 인프라', '운영 · 모니터링', 'Python · DB', '기타']

SECRET_PATTERNS = [
    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', 'IP address'),
    (r'\b[\w-]+\.(?:kcp|nhn)[\w.-]*\b', 'internal hostname'),
    (r'\.co\.kr\b', 'company domain'),
    (r'(?i)\b(password|passwd|secret_key|access_key|api_key|token)\s*[:=]\s*\S+', 'credential assignment'),
    (r'AKIA[0-9A-Z]{16}', 'AWS access key id'),
    (r'(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----', 'private key'),
]


def read(path):
    return io.open(path, encoding='utf-8').read()


def esc(s):
    return html.escape(s, quote=False)


# ---------------- minimal markdown -> html ----------------
def inline(s):
    s = esc(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<em>\1</em>', s)
    s = re.sub(r'!?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', lambda m: m.group(2) or m.group(1), s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def render_list(items):
    res, stack = [], []
    for ind, ordered, text in items:
        tag = 'ol' if ordered else 'ul'
        if not stack or ind > stack[-1][0]:
            if stack:
                res[-1] = res[-1][:-5]
            res.append('<%s>' % tag)
            stack.append((ind, tag))
            res.append('<li>%s</li>' % inline(text))
            continue
        while stack and ind < stack[-1][0]:
            res.append('</%s></li>' % stack.pop()[1])
        res.append('<li>%s</li>' % inline(text))
    while stack:
        res.append('</%s>' % stack.pop()[1])
    return ''.join(res)


def md_to_html(text):
    lines = text.split('\n')
    out, buf, i, n = [], [], 0, len(lines)

    def flush():
        if buf:
            out.append('<p>%s</p>' % inline(' '.join(buf)))
            del buf[:]

    while i < n:
        ln = lines[i]
        st = ln.strip()
        if st.startswith('```'):
            flush()
            lang = st[3:].strip()
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith('```'):
                code.append(lines[i])
                i += 1
            i += 1
            cls = ' class="lang-%s"' % esc(lang) if lang else ''
            out.append('<pre><code%s>%s</code></pre>' % (cls, esc('\n'.join(code))))
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', st)
        if m:
            flush()
            lvl = len(m.group(1))
            if lvl > 1:
                out.append('<h%d>%s</h%d>' % (lvl, inline(m.group(2)), lvl))
            i += 1
            continue
        if re.match(r'^(-{3,}|\*{3,})$', st):
            flush()
            out.append('<hr>')
            i += 1
            continue
        if st.startswith('|'):
            flush()
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            rows = [r for r in rows if not all(re.match(r'^:?-+:?$', c) for c in r)]
            if rows:
                head = ''.join('<th>%s</th>' % inline(c) for c in rows[0])
                body = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % inline(c) for c in r) for r in rows[1:])
                out.append('<div class="tbl"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (head, body))
            continue
        if st.startswith('>'):
            flush()
            q = []
            while i < n and lines[i].strip().startswith('>'):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            out.append('<blockquote>%s</blockquote>' % inline(' '.join(q)))
            continue
        if re.match(r'^(\s*)([-*+]|\d+\.)\s+(.*)$', ln):
            flush()
            items = []
            while i < n:
                mm = re.match(r'^(\s*)([-*+]|\d+\.)\s+(.*)$', lines[i])
                if mm:
                    items.append((len(mm.group(1).expandtabs(4)), mm.group(2).endswith('.'), mm.group(3)))
                    i += 1
                elif lines[i].strip() and lines[i].startswith((' ', '\t')) and items:
                    d, o, t = items[-1]
                    items[-1] = (d, o, t + ' ' + lines[i].strip())
                    i += 1
                else:
                    break
            out.append(render_list(items))
            continue
        if not st:
            flush()
            i += 1
            continue
        buf.append(st)
        i += 1
    flush()
    return '\n'.join(out)


# ---------------- notes ----------------
def parse_frontmatter(raw):
    meta, body = {}, raw
    if raw.startswith('---'):
        end = raw.find('\n---', 3)
        if end > 0:
            for ln in raw[3:end].split('\n'):
                if ':' in ln:
                    k, v = ln.split(':', 1)
                    meta[k.strip()] = v.strip()
            body = raw[end + 4:]
    return meta, body


def category(meta):
    explicit = meta.get('카테고리', '').strip()
    if explicit in CATEGORY_ORDER:
        return explicit
    cls = meta.get('분류', '')
    for prefix, cat in CATEGORY_RULES:
        if cls.startswith(prefix):
            return cat
    return '기타'


def excerpt(body):
    m = re.search(r'^##\s+한 줄 정의\s*\n+(.+)$', body, re.M)
    ex = m.group(1) if m else ''
    if not ex:
        for ln in body.split('\n'):
            s = ln.strip()
            if s.startswith('>'):
                ex = s.lstrip('> ')
                break
            if s and not s.startswith(('#', '```', '|', '-', '*', '1')):
                ex = s
                break
    ex = re.sub(r'[`*>]', '', ex).strip()
    return ex[:108].rstrip() + '…' if len(ex) > 110 else ex


def scan_secrets(path, text):
    hits = []
    for pat, label in SECRET_PATTERNS:
        for m in re.finditer(pat, text):
            line = text.count('\n', 0, m.start()) + 1
            hits.append('%s:%d  %s  %r' % (os.path.basename(path), line, label, m.group(0)[:40]))
    return hits


def load_notes(src):
    notes, problems = [], []
    for sub, kind in SOURCES:
        for path in sorted(glob.glob(os.path.join(src, sub, '*.md'))):
            raw = read(path)
            meta, body = parse_frontmatter(raw)
            if meta.get('publish', '').lower() != 'true':
                continue
            problems += scan_secrets(path, raw)
            name = os.path.splitext(os.path.basename(path))[0]
            m = re.search(r'^#\s+(.+)$', body, re.M)
            title = m.group(1).strip() if m else name
            dm = re.search(r'(\d{4}-\d{2}-\d{2})', meta.get('출처', '') + ' ' + meta.get('date', ''))
            date = dm.group(1) if dm else datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
            slug = re.sub(r'[^\w가-힣]+', '-', name).strip('-').lower()
            notes.append(dict(title=title, date=date, cat=category(meta), kind=kind,
                              excerpt=excerpt(body), slug=slug, html=md_to_html(body)))
    notes.sort(key=lambda d: (d['date'], d['title']), reverse=True)
    return notes, problems


# ---------------- templates ----------------
def site_chrome(index):
    head = re.search(r'(<link rel="preconnect".*?<link rel="stylesheet" href="assets/style.css">)', index, re.S).group(1)
    icons = re.search(r'(<svg width="0" height="0".*?</defs></svg>)', index, re.S).group(1)
    nav = re.search(r'(<nav class="nav">.*?</nav>)', index, re.S).group(1)
    footer = re.search(r'(<footer class="foot">.*?</footer>)', index, re.S).group(1)
    head = head.replace('assets/style.css', '../assets/style.css')
    nav = nav.replace('href="#', 'href="../index.html#').replace('href="notes/index.html"', 'href="index.html"')
    nav = re.sub(r'<button class="brand" data-home type="button">(.*?)</button>', r'<a class="brand" href="../index.html">\1</a>', nav, count=1, flags=re.S)
    nav = re.sub(r'<div class="langtoggle".*?</div>', '', nav, flags=re.S)
    footer = footer.replace('href="notes/index.html"', 'href="index.html"')
    return head, icons, nav, footer


def page(chrome, title, body):
    head, icons, nav, footer = chrome
    return '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s · Zoe Choi</title>
%s
</head>
<body class="notes-body">
%s
%s
%s
%s
<script>document.querySelectorAll('.rv').forEach(function(e){e.classList.add('in')});</script>
</body>
</html>
''' % (esc(title), head, icons, nav, body, footer)


def row(nt):
    kind_cls = 'guide' if nt['kind'] == '가이드' else 'concept'
    return '''      <li class="note-row" data-cat="%s">
        <a href="%s.html">
          <span class="note-row__meta"><span class="note-row__date">%s</span><span class="note-row__kind note-row__kind--%s">%s</span><span class="note-row__cat">%s</span></span>
          <strong class="note-row__title">%s</strong>
          <span class="note-row__ex">%s</span>
        </a>
      </li>''' % (esc(nt['cat']), nt['slug'], nt['date'], kind_cls, nt['kind'], esc(nt['cat']), esc(nt['title']), esc(nt['excerpt']))


def list_body(notes):
    chips = '<button type="button" class="chip is-on" data-filter="*">전체 <i>%d</i></button>' % len(notes)
    for c in CATEGORY_ORDER:
        k = sum(1 for x in notes if x['cat'] == c)
        if k:
            chips += '<button type="button" class="chip" data-filter="%s">%s <i>%d</i></button>' % (esc(c), esc(c), k)
    rows = '\n'.join(row(n) for n in notes) if notes else '      <li class="note-empty">아직 올린 노트가 없습니다. 정리되는 대로 하나씩 추가합니다.</li>'
    return '''
<main class="notes-main">
  <section class="band band--white">
    <div class="wrap">
      <div class="notes-head rv">
        <span class="eyebrow">노트</span>
        <h1>업무하면서 모르던 것들</h1>
        <p class="lead">일하다 막힌 개념을 짧게 정리합니다. 한 줄 정의로 시작해, 왜 중요한지와 예시까지.</p>
      </div>
      <div class="chips rv">%s</div>
      <ul class="note-list rv">
%s
      </ul>
    </div>
  </section>
</main>
<script>
(function(){
  var chips=document.querySelectorAll('.chip'), rows=document.querySelectorAll('.note-row');
  chips.forEach(function(c){c.addEventListener('click',function(){
    chips.forEach(function(x){x.classList.toggle('is-on',x===c)});
    var f=c.dataset.filter; rows.forEach(function(r){r.hidden=(f!=='*'&&r.dataset.cat!==f)});
  })});
})();
</script>''' % (chips, rows)


def note_body(nt):
    return '''
<main class="notes-main">
  <section class="band band--white">
    <div class="wrap">
      <a class="backlink" href="index.html"><svg viewBox="0 0 24 24"><use href="#i-arrow-left"/></svg>노트 목록</a>
      <div class="note-head rv">
        <span class="eyebrow">%s · %s</span>
        <h1>%s</h1>
        <div class="detail__meta"><span><b>정리</b> %s</span></div>
      </div>
      <article class="prose rv">
%s
      </article>
    </div>
  </section>
</main>''' % (esc(nt['cat']), nt['kind'], esc(nt['title']), nt['date'], nt['html'])


def teaser_block(notes):
    if not notes:
        return '  <!-- notes:teaser:start -->\n  <!-- notes:teaser:end -->'
    items = '\n'.join('''          <li><a href="notes/%s.html"><span class="teaser__cat">%s</span><strong>%s</strong><span class="teaser__ex">%s</span></a></li>''' % (
        n['slug'], esc(n['cat']), esc(n['title']), esc(n['excerpt'])) for n in notes[:3])
    return '''  <!-- notes:teaser:start -->
  <section class="band band--white" id="notes">
    <div class="wrap">
      <div class="teaser rv">
        <div class="teaser__head">
          <span class="eyebrow"><span class="ko">노트</span><span class="en">Notes</span></span>
          <h2><span class="ko">최근에 정리한 것</span><span class="en">Recently written up</span></h2>
          <p><span class="ko">업무하면서 모르던 개념을 짧게 정리합니다.</span><span class="en">Short write-ups of things I had to learn on the job.</span></p>
          <a class="teaser__more" href="notes/index.html"><span class="ko">전체 노트 %d개 보기</span><span class="en">All %d notes</span><svg viewBox="0 0 24 24"><use href="#i-arrow-right"/></svg></a>
        </div>
        <ul class="teaser__list">
%s
        </ul>
      </div>
    </div>
  </section>
  <!-- notes:teaser:end -->''' % (len(notes), len(notes), items)


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', help='local checkout of obsidian_public (default: clone %s)' % REPO_URL)
    args = ap.parse_args()

    tmp = None
    src = args.src
    if not src:
        tmp = tempfile.mkdtemp(prefix='obsidian_public_')
        subprocess.run(['git', 'clone', '--depth', '1', '--quiet', REPO_URL, tmp], check=True)
        src = tmp
    try:
        notes, problems = load_notes(src)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    if problems:
        print('ABORT: possible sensitive content in publishable notes:')
        for p in problems:
            print('  ' + p)
        sys.exit(1)

    index_path = os.path.join(ROOT, 'index.html')
    index = io.open(index_path, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in index else '\n'

    teaser_re = re.compile(r'  <!-- notes:teaser:start -->.*?<!-- notes:teaser:end -->', re.S)
    if not teaser_re.search(index):
        print('ABORT: teaser markers missing in index.html')
        sys.exit(1)
    index = teaser_re.sub(lambda m: teaser_block(notes).replace('\n', nl), index)
    io.open(index_path, 'w', encoding='utf-8', newline='').write(index)

    chrome = site_chrome(index.replace('\r\n', '\n'))
    out_dir = os.path.join(ROOT, 'notes')
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    io.open(os.path.join(out_dir, 'index.html'), 'w', encoding='utf-8', newline='').write(page(chrome, '노트', list_body(notes)).replace('\n', nl))
    for nt in notes:
        io.open(os.path.join(out_dir, nt['slug'] + '.html'), 'w', encoding='utf-8', newline='').write(page(chrome, nt['title'], note_body(nt)).replace('\n', nl))

    for nt in notes:
        print('%s  %-20s %-4s %s' % (nt['date'], nt['cat'], nt['kind'], nt['slug']))
    print('built %d notes -> notes/, teaser updated in index.html' % len(notes))


if __name__ == '__main__':
    main()

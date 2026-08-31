import argparse
import html
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from glob import glob


MEDIA_TYPES = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp',
}

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    '  <rootfiles>\n'
    '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
    '  </rootfiles>\n'
    '</container>\n'
)

CSS = (
    'img { display: block; max-width: 100%; margin: 0 auto; }\n'
    'h1, h2 { text-align: center; font-weight: bold; margin: 1em 0; }\n'
    'h1 { font-size: 2em; }\n'
    'h2 { font-size: 1.5em; }\n'
)

# One comic: (dir name, title, authors, reading direction, chapters[(name, page files)])
Book = tuple[str, str, str, str, list[tuple[str, list[str]]]]


def parse_info(comic_dir: str) -> dict[str, str] | None:
    # info.txt is written only after a comic is fully downloaded, so it doubles
    # as the completeness marker.
    info_path = f'{comic_dir}/info.txt'
    if not os.path.isfile(info_path):
        return None
    info: dict[str, str] = {}
    with open(info_path, 'r', encoding='utf-8') as f:
        for line in f:
            if '：' in line:
                key, value = line.split('：', 1)
                info[key.strip()] = value.strip()
    return info or None


def chapter_order(name: str) -> tuple[int, str]:
    m = re.match(r'(\d+)-', name)
    return (int(m.group(1)) if m else 1 << 30, name)


def collect_chapters(comic_dir: str) -> tuple[list[tuple[str, list[str]]], list[str]]:
    # Every subdirectory is an episode and must hold a gap-free run of P{n}.* pages.
    chapters: list[tuple[str, list[str]]] = []
    problems: list[str] = []
    for name in sorted(os.listdir(comic_dir), key=chapter_order):
        path = f'{comic_dir}/{name}'
        if not os.path.isdir(path):
            continue
        pages: dict[int, str] = {}
        for f in glob(f'{path}/P*.*'):
            if f.endswith('.tmp'):
                problems.append(f'{name} 有未写完的临时文件')
                continue
            m = re.match(r'P(\d+)\.', os.path.basename(f))
            if m:
                pages.setdefault(int(m.group(1)), f)
        if not pages:
            problems.append(f'{name} 没有已完成的页面')
            continue
        missing = [str(n) for n in range(1, max(pages) + 1) if n not in pages]
        if missing:
            problems.append(f'{name} 缺第 {"、".join(missing)} 页')
        chapters.append((name, [pages[n] for n in sorted(pages)]))
    if not chapters:
        problems.append('没有任何章节')
    return chapters, problems


def xhtml(title: str, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        '  <head>\n'
        f'    <title>{html.escape(title)}</title>\n'
        '    <link rel="stylesheet" type="text/css" href="../style.css"/>\n'
        '  </head>\n'
        '  <body>\n'
        + body + '\n'
        '  </body>\n'
        '</html>\n')


def build_epub(books: list[Book], out_path: str) -> None:
    volume_title = books[0][1] if len(books) == 1 else '泰拉记事社'
    volume_id = uuid.uuid5(uuid.NAMESPACE_URL, f'terra-historicus/{volume_title}')
    creator_xml = (f'    <dc:creator>{html.escape(books[0][2])}</dc:creator>\n'
                   if len(books) == 1 and books[0][2] else '')
    root = './terra-historicus'
    # One spine for the whole volume: honour right-to-left only when every
    # included comic reads that way.
    progression = 'rtl' if {b[3] for b in books} == {'right'} else 'ltr'

    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="css" href="style.css" media-type="text/css"/>',
    ]
    spine: list[str] = []
    toc: list[str] = []
    # Many readers still only read the EPUB 2 NCX table of contents, so the
    # nav.xhtml above is mirrored into toc.ncx.
    nav_points: list[str] = []
    play_order = 0
    documents: list[tuple[str, str]] = []
    images: list[tuple[str, str]] = []

    for bi, (dirname, title, _, _, chapters) in enumerate(books, 1):
        bid = f'b{bi:03d}'
        covers = [f for f in glob(f'{root}/{dirname}/封面.*') if not f.endswith('.tmp')]
        entry_href = ''
        book_play = 0
        book_src = ''
        if covers:
            ext = os.path.basename(covers[0]).split('.')[-1].lower()
            manifest.append(f'<item id="img-{bid}" href="img/{bid}/cover.{ext}" '
                            f'media-type="{MEDIA_TYPES.get(ext, "application/octet-stream")}"/>')
            images.append((covers[0], f'OEBPS/img/{bid}/cover.{ext}'))
            manifest.append(f'<item id="{bid}" href="text/{bid}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="{bid}"/>')
            entry_href = f'text/{bid}.xhtml'
            play_order += 1
            book_play, book_src = play_order, entry_href
            documents.append((entry_href, xhtml(
                title, f'    <h1>{html.escape(title)}</h1>\n'
                       f'    <img src="../img/{bid}/cover.{ext}" alt="cover"/>')))

        chapter_entries: list[str] = []
        chapter_points: list[str] = []
        for ci, (name, pages) in enumerate(chapters, 1):
            cid = f'{bid}-c{ci:03d}'
            imgs: list[str] = []
            for p, page in enumerate(pages, 1):
                ext = os.path.basename(page).split('.')[-1].lower()
                href = f'img/{bid}/c{ci:03d}/p{p:03d}.{ext}'
                manifest.append(f'<item id="img-{cid}-{p:03d}" href="{href}" '
                                f'media-type="{MEDIA_TYPES.get(ext, "application/octet-stream")}"/>')
                images.append((page, f'OEBPS/{href}'))
                imgs.append(f'    <img src="../{href}" alt="{p}"/>')
            manifest.append(f'<item id="{cid}" href="text/{cid}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="{cid}"/>')
            play_order += 1
            if not book_play:
                book_play, book_src = play_order, f'text/{cid}.xhtml'
            entry_href = entry_href or f'text/{cid}.xhtml'
            chapter_entries.append(f'        <li><a href="text/{cid}.xhtml">{html.escape(name)}</a></li>')
            chapter_points.append(
                f'      <navPoint id="{cid}" playOrder="{play_order}">\n'
                f'        <navLabel><text>{html.escape(name)}</text></navLabel>\n'
                f'        <content src="text/{cid}.xhtml"/>\n'
                '      </navPoint>')
            documents.append((f'text/{cid}.xhtml',
                              xhtml(name, f'    <h2>{html.escape(name)}</h2>\n' + '\n'.join(imgs))))
        nav_points.append(
            f'    <navPoint id="{bid}" playOrder="{book_play}">\n'
            f'      <navLabel><text>{html.escape(title)}</text></navLabel>\n'
            f'      <content src="{book_src}"/>\n'
            + '\n'.join(chapter_points) + '\n'
            '    </navPoint>')
        toc.append(
            '      <li>\n'
            f'        <a href="{entry_href}">{html.escape(title)}</a>\n'
            '        <ol>\n' + '\n'.join(chapter_entries) + '\n        </ol>\n'
            '      </li>')

    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        '  <head>\n'
        f'    <title>{html.escape(volume_title)}</title>\n'
        '    <link rel="stylesheet" type="text/css" href="style.css"/>\n'
        '  </head>\n'
        '  <body>\n'
        '    <nav epub:type="toc" id="toc">\n'
        f'      <h1>{html.escape(volume_title)}</h1>\n'
        '      <ol>\n'
        + '\n'.join(toc) + '\n'
        '      </ol>\n'
        '    </nav>\n'
        '  </body>\n'
        '</html>\n')

    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        '  <head>\n'
        f'    <meta name="dtb:uid" content="urn:uuid:{volume_id}"/>\n'
        '    <meta name="dtb:depth" content="2"/>\n'
        '  </head>\n'
        f'  <docTitle><text>{html.escape(volume_title)}</text></docTitle>\n'
        '  <navMap>\n'
        + '\n'.join(nav_points) + '\n'
        '  </navMap>\n'
        '</ncx>\n')

    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="zh">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'    <dc:identifier id="book-id">urn:uuid:{volume_id}</dc:identifier>\n'
        f'    <dc:title>{html.escape(volume_title)}</dc:title>\n'
        + creator_xml +
        '    <dc:language>zh</dc:language>\n'
        f'    <meta property="dcterms:modified">{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}</meta>\n'
        '  </metadata>\n'
        '  <manifest>\n'
        '    ' + '\n    '.join(manifest) + '\n'
        '  </manifest>\n'
        f'  <spine toc="ncx" page-progression-direction="{progression}">\n'
        '    ' + '\n    '.join(spine) + '\n'
        '  </spine>\n'
        '</package>\n')

    # JPEG/PNG payloads are already compressed; level 1 keeps the CPU cost of
    # zipping a multi-GB volume negligible.
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        # The mimetype entry must come first and be stored uncompressed (EPUB spec).
        zf.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        zf.writestr('META-INF/container.xml', CONTAINER)
        zf.writestr('OEBPS/style.css', CSS)
        for disk_path, arc_path in images:
            zf.write(disk_path, arc_path)
        for path, doc in documents:
            zf.writestr(f'OEBPS/{path}', doc)
        zf.writestr('OEBPS/nav.xhtml', nav)
        zf.writestr('OEBPS/toc.ncx', ncx)
        zf.writestr('OEBPS/content.opf', opf)


def collect_books(patterns: list[re.Pattern[str]] | None = None) -> list[Book]:
    # Complete local comics only; incomplete ones are reported and skipped.
    root = './terra-historicus'
    books: list[Book] = []
    for entry in sorted(os.listdir(root)):
        comic_dir = f'{root}/{entry}'
        if not os.path.isdir(comic_dir):
            continue
        info = parse_info(comic_dir)
        if info is None:
            print(f'警告：{entry} 缺少 info.txt（上次下载未完成），跳过')
            continue
        chapters, problems = collect_chapters(comic_dir)
        problems += [f'顶层有未写完的临时文件 {os.path.basename(t)}' for t in glob(f'{comic_dir}/*.tmp')]
        if problems:
            print(f'警告：{entry} 不完整（{"；".join(problems)}），跳过')
            continue
        books.append((entry, info.get('作品标题', entry), info.get('作者', ''),
                      info.get('阅读方向', 'left'), chapters))
    if patterns:
        books = [b for b in books if any(p.search(b[1]) or p.search(b[0]) for p in patterns)]
    return books


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Build EPUB file(s) from downloaded Terra Historicus comics.')
    parser.add_argument('--mode', '-m', choices=['single', 'per-comic'], default='per-comic',
                        help='single: all comics in one volume; per-comic: one file per comic (default)')
    parser.add_argument('--filter', '-f', action='append', default=[], metavar='REGEX',
                        help='only include comics whose title matches REGEX (repeatable, any match counts)')
    args = parser.parse_args()
    try:
        patterns = [re.compile(f) for f in args.filter]
    except re.error as e:
        raise SystemExit(f'无效的正则：{e}')

    books = collect_books(patterns)
    if not books:
        print('没有匹配的完整本地漫画，未生成 epub')
        return

    out_dir = './epub-output'
    os.makedirs(out_dir, exist_ok=True)
    if args.mode == 'single':
        out_path = f'{out_dir}/terra-historicus.epub'
        build_epub(books, out_path)
        print(f'{len(books)} 部漫画、{sum(len(b[4]) for b in books)} 章 → {out_path}')
    else:
        for book in books:
            out_path = f'{out_dir}/{book[0]}.epub'
            build_epub([book], out_path)
            print(f'{book[1]}：{len(book[4])} 章 → {out_path}')


if __name__ == '__main__':
    main()

import os
from glob import glob

from epub import Book, collect_books


def link_comic(comic: Book, flat_root: str) -> None:
    dirname, _, _, _, chapters = comic
    comic_dir = f'./terra-historicus/{dirname}'
    flat_dir = f'{flat_root}/{dirname}'
    os.makedirs(flat_dir, exist_ok=True)

    # Hard links share storage with the source tree, so the flat copy costs no
    # extra space. Existing links are left alone, which makes re-runs
    # incremental: only pages new since the last run get linked.
    def link(src: str, dst: str) -> None:
        try:
            os.link(src, dst)
        except FileExistsError:
            pass

    # One flat directory per comic, ordered by filename: P{chapter}-{page}
    # with the cover as chapter 0000 page 0000. Readers that cannot handle
    # nested directories get correct page order from the name sort alone.
    covers = [f for f in glob(f'{comic_dir}/封面.*') if not f.endswith('.tmp')]
    if covers:
        ext = os.path.basename(covers[0]).split('.')[-1]
        link(covers[0], f'{flat_dir}/P0000-0000.{ext}')
    for ci, (_, pages) in enumerate(chapters, 1):
        for p, page in enumerate(pages, 1):
            ext = os.path.basename(page).split('.')[-1]
            link(page, f'{flat_dir}/P{ci:04d}-{p:04d}.{ext}')


def main() -> None:
    flat_root = './terra-historicus-flat'
    os.makedirs(flat_root, exist_ok=True)
    books = collect_books()
    if not books:
        print('没有完整的本地漫画，未生成目录')
        return
    for book in books:
        link_comic(book, flat_root)
        print(f'{book[0]}：{len(book[4])} 章 → {flat_root}/{book[0]}')
    print(f'{len(books)} 部漫画 → {flat_root}')


if __name__ == '__main__':
    main()

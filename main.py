import requests
from tqdm import tqdm
import json
import time
import os
import re
from glob import glob


class TerraHistoricus:

    def __init__(self):
        self.headers = {
            'Referer': 'https://terra-historicus.hypergryph.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/100.0.4896.75 Safari/537.36 Edg/100.0.1185.36 '
        }

    def __get_comics_cid(self):
        response = requests.get(
            url='https://terra-historicus.hypergryph.com/api/comic',
            headers=self.headers
        )
        comic_list = json.loads(response.text)['data']
        for comic in comic_list:
            yield comic['cid']

    def __get_comic_info(self):
        for cid in self.__get_comics_cid():
            response = requests.get(
                url=f'https://terra-historicus.hypergryph.com/api/comic/{cid}',
                headers=self.headers
            )
            comic_info = json.loads(response.text)['data']
            yield comic_info

    def __get_comic_pages(self, parent_cid: str, cid: str) -> int:
        response = requests.get(
            url=f'https://terra-historicus.hypergryph.com/api/comic/{parent_cid}/episode/{cid}',
            headers=self.headers
        )
        return len(json.loads(response.text)['data']['pageInfos'])

    def __get_comic_page_url(self, parent_cid: str, cid: str, num: int) -> str:
        response = requests.get(
            url=f'https://terra-historicus.hypergryph.com/api/comic/{parent_cid}/episode/{cid}/page?pageNum={num}',
            headers=self.headers
        )
        return json.loads(response.text)['data']['url']

    def save_data(self):
        path_detection = re.compile(r'[\\/:*?<>"|]')

        def is_path(path: str) -> None:
            if not os.path.exists(path):
                os.mkdir(path)

        def url_download(url: str, headers: dict[str, str], name: str, path: str) -> None:
            response = requests.get(
                url=url,
                headers=headers
            )
            # Atom
            tmp_path = f'{path}/{name}.tmp'
            with open(tmp_path, 'wb') as file:
                file.write(response.content)
            os.replace(tmp_path, f'{path}/{name}')

        first_path = './terra-historicus'
        is_path(first_path)
        for comic_info in self.__get_comic_info():
            second_path = f'{first_path}/{path_detection.sub("!", comic_info["title"])}'
            is_path(second_path)

            if not os.path.isfile(f'{second_path}/封面.{comic_info["cover"].split(".")[-1]}'):
                url_download(
                    url=comic_info['cover'],
                    headers=self.headers,
                    name=f'封面.{comic_info["cover"].split(".")[-1]}',
                    path=second_path
                )

            old_time = 0
            if os.path.isfile(second_path + '/info.txt'):
                try:
                    with open(second_path + '/info.txt', 'r', encoding='utf-8') as f:
                        old_time = time.mktime(time.strptime(f.read().split('\n')[-1].split('：')[-1], '%Y-%m-%d %X'))
                except ValueError:
                    # Corrupted info.txt
                    old_time = 0
            if old_time >= comic_info['episodes'][0]['displayTime']:
                print(f'{comic_info["title"]}已经是最新')
                continue

            i = 1
            for episode in tqdm(comic_info['episodes'][::-1], desc=f'{comic_info["title"]}'):
                upgrade_time = episode['displayTime']
                if old_time >= upgrade_time:
                    i += 1
                    continue
                third_path = f'{second_path}/{i}-{path_detection.sub("!", str(episode["shortTitle"]))} ' \
                             f'{path_detection.sub("!", str(episode["title"]))}'
                is_path(third_path)
                page_nums = self.__get_comic_pages(comic_info['cid'], episode['cid'])
                i += 1
                
                for p in range(1, page_nums + 1):
                    # Zero-padded page names (P0001) keep filename sort order
                    # stable for epub building and local comic readers.
                    if [f for f in glob(f'{third_path}/P{p:04d}.*') if not f.endswith('.tmp')]:
                        continue
                    url = self.__get_comic_page_url(comic_info['cid'], episode['cid'], p)
                    url_download(
                        url=url,
                        headers=self.headers,
                        name=f'P{p:04d}.{url.split(".")[-1]}',
                        path=third_path
                    )

            with open(second_path + '/info.txt', 'w', encoding='utf-8') as f:
                f.write(f'作品标题：{comic_info["title"]}\n')
                f.write(f'作品副标题：{comic_info["subtitle"]}\n')
                f.write(f'作者：{"、".join(comic_info["authors"])}\n')
                # f-string表达式不能出现反斜杠，用format方法替换
                f.write('作品介绍：{}\n'.format(
                    comic_info['introduction'].replace("\n", "\n                ")))
                f.write(f'作品标签：{"、".join(comic_info["keywords"])}\n')
                f.write(f'阅读方向：{comic_info["direction"]}\n')
                f.write(f'发布时间：{time.strftime("%Y-%m-%d %X", time.localtime(comic_info["updateTime"]))}\n')
                f.write(f'更新时间：{time.strftime("%Y-%m-%d %X", time.localtime(comic_info["episodes"][0]["displayTime"]))}')


if __name__ == '__main__':
    TH = TerraHistoricus()
    TH.save_data()
    pass

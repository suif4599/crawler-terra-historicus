# crawler-terra-historicus

本项目 fork 自 [FrothierNine346/crawler-terra-historicus](https://github.com/FrothierNine346/crawler-terra-historicus.git)，用于爬取泰拉记事社官网所有漫画

原项目功能：

- 爬取漫画
- 爬取漫画介绍
- 爬取漫画封面

本项目新增功能：

- 更好的断点续传
- 导出为 Epub
- 创建扁平视图便于 Venera 等阅读器导入

## 使用方法

```bash
pixi run dl # 爬取漫画
pixi run epub -f 莱茵 # 导出匹配 "莱茵" 的漫画
pixi run epub -m single # 导出所有漫画至单个 Epub 文件
pixi run venera # 生成扁平视图
```

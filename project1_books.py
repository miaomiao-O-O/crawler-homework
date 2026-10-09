# -*- coding: utf-8 -*-
"""
项目一 · 静态页整站抓取 —— books.toscrape.com
目标：把整站约 1000 本书整理成表格
字段：书名、价格、评分、库存、详情页链接
关键概念：
  1. 按"位置 + 属性"从网页结构中提取字段（article.product_pod）
  2. 识别 URL 翻页规律后循环遍历全部页面（page-1.html → page-2.html ...）
  3. 清理符号、空格（£、多余空白）
  4. 不遗漏最后一页：用 li.next 是否存在判断是否还有下一页，并用总条数核对
"""
import time
import csv

import requests
from bs4 import BeautifulSoup

BASE = "https://books.toscrape.com"
# 站点无 robots.txt（404），属于公开可抓取教学站点；仍控制请求频率
HEADERS = {"User-Agent": "Mozilla/5.0 (homework-scraper; polite/0.5s)"}
DELAY = 0.5  # 每页请求间隔（秒），避免压垮站点

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def clean_price(text):
    """清理价格：去掉英镑符号与空白，转成可计算的浮点数"""
    return float(text.replace("£", "").replace(",", "").strip())


def parse_page(soup):
    """从一个已解析的页面中提取 20 本书"""
    books = []
    for art in soup.select("article.product_pod"):
        title = art.h3.a["title"].strip()
        href = art.h3.a["href"]
        # 详情页链接：相对路径补齐为完整 URL
        url = BASE + "/catalogue/" + href if not href.startswith("http") else href
        price = clean_price(art.select_one("p.price_color").text)
        rating_cls = [c for c in art.select_one("p.star-rating")["class"] if c != "star-rating"]
        rating = RATING_MAP.get(rating_cls[0], 0) if rating_cls else 0
        stock = art.select_one("p.instock.availability").text.strip()
        books.append({"书名": title, "价格": price, "评分": rating, "库存": stock, "详情页链接": url})
    return books


def main():
    all_books = []
    page_no = 1
    url = f"{BASE}/catalogue/page-{page_no}.html"

    while True:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        # 关键：传 resp.content（原始字节）而非 resp.text，让 BeautifulSoup 按
        # 页面 meta 声明的 charset 自动解码，避免 £ → Â 这类编码乱码
        soup = BeautifulSoup(resp.content, "html.parser")
        books = parse_page(soup)
        if not books:
            break
        all_books.extend(books)
        print(f"第 {page_no} 页：抓到 {len(books)} 本，累计 {len(all_books)} 本")
        # 判断是否还有下一页（不遗漏最后一页的关键）
        next_a = soup.select_one("li.next a")
        if next_a is None:
            break
        url = BASE + "/catalogue/" + next_a["href"]
        page_no += 1
        time.sleep(DELAY)

    # 保存为 CSV（UTF-8 with BOM，Excel 打开不乱码）
    with open("books.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["书名", "价格", "评分", "库存", "详情页链接"])
        writer.writeheader()
        writer.writerows(all_books)

    # 完整性核对：books.toscrape.com 共 1000 本（50 页 × 20 本）
    print("=" * 50)
    print(f"共抓取 {len(all_books)} 本，遍历 {page_no} 页")
    assert len(all_books) == 1000, f"条数与站点总书量不一致！实际 {len(all_books)} 条"
    print("✔ 完整性核对通过：条数与站点总书量（1000 条）一致")
    # 简单抽查：表格无缺失单元格
    missing = [b for b in all_books if not all(v != "" and v is not None for v in b.values())]
    print("✔ 缺失单元格检查：", "无缺失" if not missing else f"发现 {len(missing)} 条缺失")
    print("样例（前 3 条）：")
    for b in all_books[:3]:
        print(" ", b)


if __name__ == "__main__":
    main()
#（注：内容由AI生成）

# -*- coding: utf-8 -*-
"""
项目三 · 动态页：内容"等一等才出现" —— quotes.toscrape.com
练习网址：
  先练 /js      —— 名言内容由页面脚本填充
  再练 /scroll  —— 向下滚动才继续加载的"无限滚动"页面
需提取字段：名言内容 + 作者
过关标准：成功获取普通方法无法抓取的内容；能用一句话讲清内容的加载机制。

为什么 requests 拿不到？
  服务器第一次返回的 HTML 是"空房间"：只有 <script> 施工说明。
  浏览器会照着说明去取"家具"（真正的内容）并渲染；而 Python 的
  requests.get(url).text 只搬回"空房间"，不执行 JS，所以解析不到内容。

应对策略（本脚本演示两条）：
  i.  /js 页：内容就内嵌在页面 <script> 里的 var data=[...]，直接解析该 JSON
  ii. /scroll 页：F12 → Network → 筛选 XHR 可发现数据接口 /api/quotes，
      直接用 Python 请求该接口拿 JSON（更聪明的做法，跳过渲染）
"""
import csv
import json
import re
import time

import requests

BASE = "https://quotes.toscrape.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (homework-scraper; polite)", "Accept": "application/json"}
DELAY = 0.5


def get_quotes_from_js(page_slug):
    """策略 i：从 /js 页面的内联脚本 var data=[...] 中解析名言"""
    url = f"{BASE}/{page_slug}" if page_slug == "js" else f"{BASE}/js/{page_slug}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    m = re.search(r"var\s+data\s*=\s*(\[.*?\]);", r.text, re.S)
    if not m:
        raise ValueError("未在页面中找到 var data=[...]")
    data = json.loads(m.group(1))
    out = [{"名言": q["text"], "作者": q["author"]["name"]} for q in data]
    print(f"  ✔ 从内联脚本解析 {page_slug} 页名言 {len(out)} 条（内容来源：页面 <script> 内嵌 JSON）")
    return out


def get_quotes_from_api():
    """策略 ii：直接请求 /api/quotes?page=N 数据接口（/scroll 页背后的 XHR）"""
    all_q, page = [], 1
    while True:
        r = requests.get(f"{BASE}/api/quotes", params={"page": page}, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        page_q = [{"名言": q["text"], "作者": q["author"]["name"]} for q in data["quotes"]]
        if not page_q:
            break
        all_q.extend(page_q)
        print(f"  ✔ API 第 {page} 页：{len(page_q)} 条，累计 {len(all_q)} 条")
        page += 1
        time.sleep(DELAY)
    print(f"  → 接口地址：{BASE}/api/quotes?page=N（浏览器 Network 面板 XHR 里能看到它）")
    return all_q


def main():
    print("=" * 60)
    print("【演示】为什么 requests 拿不到 /js 页内容")
    shell = requests.get(f"{BASE}/js", headers=HEADERS, timeout=20).text
    n_in_html = len(re.findall(r'class="text"', shell))
    print(f"  普通 requests.get('/js').text 里能找到的名言标签：{n_in_html} 条 → 空壳确认")
    print("  一句话机制：页面内容由 JavaScript 在浏览器里渲染填充，requests 不执行 JS，所以只拿到空 HTML；")
    print("  而 /scroll 页则是滚动时由 JS 向 /api/quotes 接口发 AJAX 请求取数。")

    print("=" * 60)
    print("【策略 i】/js 页：解析内联脚本 var data=[...]")
    js_quotes = get_quotes_from_js("js")
    # 若存在 /js/2 等分页，继续（该站 /js 通常只有一页 10 条）
    # 保存
    with open("quotes_js.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["名言", "作者"])
        w.writeheader()
        w.writerows(js_quotes)
    print(f"  ✔ 已保存 quotes_js.csv（{len(js_quotes)} 条）")

    print("=" * 60)
    print("【策略 ii】/scroll 页背后的接口：/api/quotes 直接取 JSON")
    api_quotes = get_quotes_from_api()
    with open("quotes_scroll.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["名言", "作者"])
        w.writeheader()
        w.writerows(api_quotes)
    print(f"  ✔ 已保存 quotes_scroll.csv（{len(api_quotes)} 条）")

    print("=" * 60)
    print("样例展示（API 前 3 条）：")
    for q in api_quotes[:3]:
        print(f"  - {q['作者']}: {q['名言'][:60]}…")
    print(f"合计获取名言 {len(js_quotes) + len(api_quotes)} 条，去重后 {len({q['名言'] for q in js_quotes + api_quotes})} 条")
    print("✔ 过关：普通方法（requests 直接拿 HTML）抓不到的内容，已通过解析脚本数据 / 直连数据接口成功获取")


if __name__ == "__main__":
    main()
#（注：内容由AI生成）

# -*- coding: utf-8 -*-
"""
项目二 · 脏数据清洗 + 入库 + 分析 —— 维基百科《各国人口列表》
练习网址：
  英文 https://en.wikipedia.org/wiki/List_of_sovereign_states_by_population
  中文 https://zh.wikipedia.org/wiki/各国人口列表
需提取字段：国家名 + 人口（含占世界百分比、日期等数值指标）
重点在"洗"不在"抓"：
  1. 千分位逗号、[1] 类脚注、不可见空格、数字中混杂的单位 —— 不清洗干净就只是"像数字的文字"
  2. 清洗后按类型分类存入数据库（文字→TEXT、整数→INTEGER、小数→REAL）
  3. 再读取数据进行排序、求和、取前十
  4. 缺失值处理规则：记录为 NULL / 排除出数值计算 / 单独统计条数
用法：
  python3 project2_wiki_population.py                  # 抓取维基百科（默认中文页）
  python3 project2_wiki_population.py 本地HTML文件路径  # 从本地 HTML 解析（本环境无维基百科网络时用）
"""
import re
import sys
import time
import sqlite3
import csv

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (homework-scraper; polite)", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

ZH_URL = "https://zh.wikipedia.org/wiki/各国人口列表"
EN_URLS = [
    "https://en.wikipedia.org/wiki/List_of_sovereign_states_by_population",
    "https://en.wikipedia.org/wiki/List_of_countries_by_population",
]
DB_PATH = "population.db"
FULL_CSV = "population_cleaned.csv"
TOP10_CSV = "population_top10.csv"


# ---------- 1. 数据获取 ----------
def load_html(source):
    """source 为本地文件路径则读取；否则按 URL 列表抓取，返回 (html, 来源说明)"""
    if source and source.lower().endswith((".html", ".htm")):
        import os
        if os.path.isfile(source):
            return open(source, encoding="utf-8").read(), f"本地文件 {source}"
    urls = [ZH_URL] + EN_URLS if source is None else [source]
    last_err = None
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                # 传原始字节，让 BeautifulSoup 自动识别 charset，避免乱码
                return resp.content.decode("utf-8", errors="replace"), url
            last_err = f"{url} → HTTP {resp.status_code}"
        except Exception as e:
            last_err = f"{url} → {type(e).__name__}: {str(e)[:60]}"
        time.sleep(0.5)
    raise SystemExit(f"✘ 所有数据源均获取失败。\n  {last_err}\n  提示：可先手动下载页面 HTML 存成 .html 文件，再作为参数传入本脚本。")


# ---------- 2. 核心：脏数据清洗 ----------
INVISIBLE = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x00AD, 0x2060]  # 零宽/软连字符等不可见字符
)
FOOTNOTE = re.compile(r"\[\s*[^\]]*\]")          # [1]、[注 1]、[a] 类脚注
NUMBER_ONLY = re.compile(r"^[+-]?\d[\d,.\s]*")   # 数字前缀（容忍中间的逗号/空格/点）


def clean_text(raw):
    """通用文本清理：去不可见字符、统一空白，返回干净字符串"""
    if raw is None:
        return None
    t = raw.translate(INVISIBLE)          # 去零宽空格等
    t = t.replace("\u00a0", " ").replace("\ufeff", "").replace("\u3000", " ")
    t = FOOTNOTE.sub("", t)               # 去 [1] 类脚注
    return re.sub(r"\s+", " ", t).strip()


def clean_number(raw):
    """把'像数字的文字'洗干净：返回 (数值, 清洗后的原始串)，无法识别返回 (None, ...)
    步骤：去不可见字符 → 去脚注 → 去掉数字后面的单位/杂字符 → 去千分位逗号与空格 → 转数值
    规则：'—'、''、None 视为缺失 → None
    """
    t = clean_text(raw)
    if not t or t in ("—", "-", "--", "N/A", "n/a"):
        return None, t
    m = NUMBER_ONLY.match(t)              # 只取数字前缀，丢掉混杂的单位（如"人"、"%之后"）
    num_str = m.group(0) if m else ""
    num_str = num_str.replace(",", "").replace(" ", "")
    if not num_str or num_str in ("-", ".", "+"):
        return None, t
    try:
        val = float(num_str)
        return (int(val) if val == int(val) else val), t   # 整数返回 int，小数返回 float
    except ValueError:
        return None, t


# ---------- 3. 表格定位与列映射 ----------
def find_table(soup):
    """找到同时含'国家/地区'和'人口'表头的 wikitable，返回 (table, 列下标映射)"""
    for table in soup.select("table.wikitable"):
        for tr in table.select("tr"):
            headers = [h.get_text(" ", strip=True) for h in tr.select("th")]
            if not headers:
                continue
            text = " ".join(headers).lower()
            has_country = any(k in text for k in ("国家", "地区", "country", "dependency", "territory"))
            has_pop = "人口" in text or "population" in text
            if has_country and has_pop:
                def col_idx(*keys):
                    for i, h in enumerate(headers):
                        hl = h.lower()
                        if any(k in hl for k in keys):
                            return i
                    return None
                idx = {
                    "rank": col_idx("排名", "rank", "序号"),
                    "country": col_idx("国家", "地区", "country", "dependency", "territory"),
                    "population": col_idx("人口", "population"),
                    "pct": col_idx("百分", "percent", "%", "world", "占比"),
                    "date": col_idx("日期", "date", "更新"),
                }
                return table, idx
    raise SystemExit("✘ 未找到含'国家/地区'与'人口'表头的 wikitable，页面结构可能已变化")


# ---------- 4. 入库（按类型分类存储） ----------
def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS countries")
    # 类型分类：排名/人口 → INTEGER（人口为整数），占世界百分比 → REAL（小数），国家/日期 → TEXT
    con.execute("""CREATE TABLE countries (
        rank       INTEGER PRIMARY KEY,
        country    TEXT NOT NULL,
        population INTEGER,
        pct_world  REAL,
        date       TEXT
    )""")
    return con


# ---------- 5. 主流程 ----------
def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    html, source = load_html(src)
    print(f"✔ 数据来源：{source}")

    soup = BeautifulSoup(html, "html.parser")
    table, idx = find_table(soup)
    print(f"✔ 已定位人口表，列映射：{idx}")

    records = []
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 2:                     # 跳过表头/空行
            continue
        def cell(key):
            i = idx[key]
            return clean_text(tds[i].get_text(" ", strip=True)) if i is not None and i < len(tds) else None

        country = cell("country")
        if not country:
            continue
        pop, _ = clean_number(cell("population"))
        pct, _ = clean_number(cell("pct"))
        rank_raw = cell("rank")
        rank, _ = clean_number(rank_raw) if rank_raw else (None, None)
        records.append({
            "rank": rank, "country": country, "population": pop,
            "pct_world": pct, "date": cell("date"),
        })

    # 缺失值处理规则：保留 NULL 入库，参与数值计算时自动排除，并单独统计
    con = init_db()
    con.executemany(
        "INSERT INTO countries (rank, country, population, pct_world, date) "
        "VALUES (:rank, :country, :population, :pct_world, :date)", records)
    con.commit()

    # 回读数据库进行排序、求和、取前十（验证数字列可正常参与计算）
    total_rows = con.execute("SELECT COUNT(*) FROM countries").fetchone()[0]
    missing_pop = con.execute("SELECT COUNT(*) FROM countries WHERE population IS NULL").fetchone()[0]
    missing_pct = con.execute("SELECT COUNT(*) FROM countries WHERE pct_world IS NULL").fetchone()[0]
    pop_sum = con.execute("SELECT SUM(population) FROM countries").fetchone()[0]
    top10 = con.execute(
        "SELECT rank, country, population, ROUND(pct_world, 2), date FROM countries "
        "WHERE population IS NOT NULL ORDER BY population DESC LIMIT 10").fetchall()

    print("=" * 58)
    print(f"入库 {total_rows} 行（≥100 行要求：{'✔ 通过' if total_rows >= 100 else '✘ 未达'})")
    print(f"缺失人口 {missing_pop} 行、缺失百分比 {missing_pct} 行（已按规则保留 NULL 并排除出计算）")
    print(f"全部国家人口合计（求和）：{pop_sum:,} 人（{pop_sum/1e8:.2f} 亿）")
    print("=" * 58)
    print("人口排名 TOP 10（从数据库回读排序）：")
    print(f"{'排名':<4}{'国家/地区':<32}{'人口':>18}{'占世界%':>10}  日期")
    for r, c, p, pct, d in top10:
        print(f"{r if r is not None else '-':<4}{c:<32}{p:>18,}{pct if pct is not None else '—':>10}  {d}")

    # 输出：排名结果表 + 全量清洗表
    with open(TOP10_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["排名", "国家/地区", "人口", "占世界百分比", "日期"])
        w.writerows(top10)
    with open(FULL_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["rank", "country", "population", "pct_world", "date"])
        w.writeheader()
        w.writerows(records)
    print(f"✔ 排名结果表已输出：{TOP10_CSV}；全量清洗表：{FULL_CSV}；数据库：{DB_PATH}")


if __name__ == "__main__":
    main()
#（注：内容由AI生成）

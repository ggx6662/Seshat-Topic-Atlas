#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全国院校导师库 · 全量扩充
============================

背景
----
原索引只抓了 works_count 最高的 400 所院校，占全国教育机构（3273 所）的 12%，
大量省属院校、师范学院、地方高校在北向都查不到导师。本脚本把覆盖推到全量，
并支持**断点续跑**：中途失败或限速被拒，重新运行会从上次进度继续。

用法
----
python expand_advisor_full.py                  # 全量（默认 3273 所）
python expand_advisor_full.py --limit 800      # 只补前 800 所（试跑）
python expand_advisor_full.py --per-inst 15    # 每所院校最多 15 位
python expand_advisor_full.py --rebuild        # 忽略已有进度，从头抓

产出
----
advisor_directory_full.json   全量索引（与 advisor_directory_generated.json 同结构）
advisor_full_progress.json    进度（断点续跑用）

设计取舍
--------
* 只取 CS 领域（topics.field.id:fields/17），与旧索引口径一致，便于合并。
* 先按 works_count 排序抓大的，再抓小的 —— 中途停止时也有较高价值。
* 限速：默认 8 并发 + 重试；OpenAlex 匿名额度约 10 req/s，不要调太高。
"""
import argparse
import datetime
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_advisor_index as B  # noqa: E402  复用取数与领域映射逻辑

API = "https://api.openalex.org"
MAILTO = os.environ.get("OPENALEX_MAILTO", "kb-local@example.com")
INSTITUTIONS_FILE = HERE / "institutions_cn.json"
OUT_FILE = HERE / "advisor_directory_full.json"
PROGRESS_FILE = HERE / "advisor_full_progress.json"

_lock = threading.Lock()
API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
# 有 key 时每秒上限 30 次、日额度 10000；无 key 是 10 次/秒、约 1000
_req_interval = 1.0 / 25.0 if API_KEY else 1.0 / 10.0
_last_req = [0.0]


def _throttle():
    """全局限速。有 key 时额度高得多，可以用更快的节奏。

    每次请求前统一等一个间隔，保证不会触发「每秒过快」的 429。
    """
    with _lock:
        now = time.time()
        wait = _req_interval - (now - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


def get_json(url, timeout=35, retries=5):
    """带指数退避的取数。

    OpenAlex 两种情况都会返回 429：
      1) 每秒请求过快（不扣费，稍等即可）
      2) 当日预算用尽（UTC 零点重置，当天重试无用）
    这里对前者退避重试，对后者立刻判定为「预算耗尽」并抛出，
    让调用方停下来而不是把错误刷满整个索引。
    """
    last = None
    for i in range(retries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "kb-research-local (mailto:%s)" % MAILTO,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                # 顺便记录剩余额度，方便判断离预算耗尽还有多远
                rem = resp.headers.get("X-RateLimit-Remaining")
                if rem is not None:
                    try:
                        _budget["remaining"] = int(float(rem))
                    except ValueError:
                        pass
                return data
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:
                reset = exc.headers.get("X-RateLimit-Reset") if exc.headers else None
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                # Retry-After 很大说明是日预算，不是瞬时限速
                if retry_after and _as_seconds(retry_after) > 120:
                    raise BudgetExhausted("日配额用尽，约 %d 秒后（UTC 零点）重置" % _as_seconds(retry_after))
                if reset and _as_seconds(reset) > 120 and _budget.get("remaining", 1) <= 0:
                    raise BudgetExhausted("日配额用尽，约 %d 秒后（UTC 零点）重置" % _as_seconds(reset))
                time.sleep(min(60, 2 ** (i + 1)))
                continue
            if exc.code in (400, 404):
                raise
            time.sleep(1.5 * (i + 1))
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (i + 1))
    raise last


class BudgetExhausted(RuntimeError):
    """当日 API 预算用尽，需要等到 UTC 零点后再续跑。"""


_budget = {"remaining": None}


def _as_seconds(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def fetch_authors(inst, per_page, fields):
    short_id = inst["id"].replace("https://openalex.org/", "")
    params = {
        "filter": "last_known_institutions.id:" + short_id + ",topics.field.id:fields/17",
        "sort": "cited_by_count:desc",
        "per-page": str(per_page),
        "mailto": MAILTO,
    }
    if API_KEY:
        params["api_key"] = API_KEY
    # 注意：不要加 select 参数。authors 接口的 select 不支持 topics，
    # 带上会返回 400，而 topics 正是映射研究方向的关键字段。
    data = get_json(API + "/authors?" + urllib.parse.urlencode(params))
    rows = []
    for author in data.get("results", []):
        topics = [t.get("display_name", "") for t in author.get("topics", [])[:5]]
        mapped = []
        for topic in topics:
            for field in B.map_topic_candidates(topic, fields):
                if field not in mapped:
                    mapped.append(field)
        if not mapped:
            continue
        counts = {}
        for item in mapped:
            counts[item["category"]] = counts.get(item["category"], 0) + 1
        category = max(counts, key=counts.get)
        categories = sorted(counts, key=lambda n: (-counts[n], n))
        names = []
        for item in mapped:
            if item["name"] not in names:
                names.append(item["name"])
        rows.append({
            "name": author.get("display_name", ""),
            "institution": inst["name"],
            "lab": "",
            "category": category,
            "categories": categories[:5],
            "fields": names[:8],
            "keywords": topics,
            "works_count": author.get("works_count", 0),
            "cited_by_count": author.get("cited_by_count", 0),
            "homepage": author.get("homepage_url", ""),
            "source": "OpenAlex",
            "verified": False,
            "institution_id": inst["id"],
            "province": inst.get("region", ""),
            "city": inst.get("city", ""),
            "orcid": author.get("orcid", ""),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 所（0=全部）")
    ap.add_argument("--per-inst", type=int, default=12, help="每所院校最多取多少位作者")
    ap.add_argument("--min-works", type=int, default=3)
    ap.add_argument("--workers", type=int, default=0,
                    help="并发数（0=自动：有 key 用 20，无 key 用 8）")
    ap.add_argument("--rebuild", action="store_true", help="忽略已有进度重新开始")
    args = ap.parse_args()
    if not args.workers:
        args.workers = 20 if API_KEY else 8
    print("API Key: %s  并发: %d"
          % ("已配置（日额度 10000）" if API_KEY else "未配置（日额度约 1000）", args.workers),
          flush=True)

    data = json.loads(INSTITUTIONS_FILE.read_text(encoding="utf-8"))
    institutions = data.get("institutions", [])
    # 教育机构按论文总量排序：先抓大校，中途停止时价值最高
    institutions.sort(key=lambda x: -x.get("works_count", 0))
    if args.limit:
        institutions = institutions[:args.limit]
    print("目标院校:", len(institutions), flush=True)

    done_ids = set()
    advisors = []
    if not args.rebuild and PROGRESS_FILE.exists():
        try:
            prog = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            done_ids = set(prog.get("done_ids", []))
            print("续跑：已完成", len(done_ids), "所", flush=True)
        except Exception:
            pass
    if not args.rebuild and OUT_FILE.exists():
        try:
            advisors = json.loads(OUT_FILE.read_text(encoding="utf-8")).get("advisors", [])
        except Exception:
            advisors = []

    todo = [i for i in institutions if i["id"] not in done_ids]
    print("待抓取:", len(todo), flush=True)
    fields = B.load_taxonomy_fields()

    new_rows = []
    errors = []
    lock = threading.Lock()
    t0 = time.time()

    def work(inst):
        try:
            return inst, fetch_authors(inst, args.per_inst, fields)
        except Exception as exc:
            return inst, exc

    done = 0
    budget_stop = False
    # 连续失败计数：一旦全部请求都在报错，立刻停下，
    # 避免把几千所院校都标成「已完成」却没抓到任何数据。
    consecutive_fail = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(work, inst): inst for inst in todo}
        for fut in as_completed(futures):
            inst, result = fut.result()
            with lock:
                done += 1
                if isinstance(result, Exception) and isinstance(result, BudgetExhausted):
                    # 预算用尽：不计入完成，留待下次续跑
                    budget_stop = True
                    errors.append((inst.get("name", ""), "预算用尽，待续跑"))
                    continue
                if isinstance(result, Exception):
                    # 失败一律不标记完成，下次续跑会重新尝试
                    errors.append((inst.get("name", ""), str(result)[:120]))
                    consecutive_fail += 1
                    if consecutive_fail >= 30:
                        budget_stop = True
                        print("\n✘ 连续 %d 次失败，已停止以免污染进度。最近错误：%s"
                              % (consecutive_fail, str(result)[:160]), flush=True)
                        break
                else:
                    consecutive_fail = 0
                    done_ids.add(inst["id"])
                    new_rows.extend([a for a in result
                                     if a.get("works_count", 0) >= args.min_works])
                if done % 50 == 0:
                    rate = done / max(1e-6, time.time() - t0)
                    eta = (len(todo) - done) / max(1e-6, rate)
                    print("进度 %d/%d  新导师 %d  错误 %d  速度 %.1f所/s  剩余约 %.0f 分钟"
                          % (done, len(todo), len(new_rows), len(errors), rate, eta / 60),
                          flush=True)
                    _save(done_ids, advisors + new_rows, errors, institutions)
                if budget_stop:
                    break
        if budget_stop:
            for f in futures:
                f.cancel()

    _save(done_ids, advisors + new_rows, errors, institutions)
    total = len(advisors) + len(new_rows)
    if budget_stop:
        print("\n⚠ OpenAlex 当日配额已用尽，已安全停止。", flush=True)
        print("  已完成 %d / %d 所院校，累计导师约 %d 位。"
              % (len(done_ids), len(institutions), total), flush=True)
        print("  配额在 UTC 零点重置（北京时间 08:00），届时重新运行本脚本即可从断点继续：",
              flush=True)
        print("      python expand_advisor_full.py", flush=True)
        return
    print("完成。累计导师:", total, "耗时 %.1f 分钟"
          % ((time.time() - t0) / 60), flush=True)


def _save(done_ids, advisors, errors, institutions):
    dedup = {}
    for a in advisors:
        key = (str(a.get("name", "")).strip().lower(),
               str(a.get("institution", "")).strip().lower())
        if key not in dedup:
            dedup[key] = a
    merged = sorted(dedup.values(), key=lambda x: (-x.get("cited_by_count", 0),
                                                   -x.get("works_count", 0)))
    OUT_FILE.write_text(json.dumps({
        "source": "OpenAlex",
        "generated_at": datetime.datetime.now().isoformat(timespec="minutes"),
        "institution_total": len(institutions),
        "institution_count": len(done_ids),
        "advisor_count": len(merged),
        "errors": errors[:50],
        "advisors": merged,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    PROGRESS_FILE.write_text(json.dumps({
        "updated": datetime.datetime.now().isoformat(timespec="minutes"),
        "done_ids": sorted(done_ids),
    }, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
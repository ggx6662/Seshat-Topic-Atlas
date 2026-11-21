# -*- coding: utf-8 -*-
"""把公开站（competition/site/data）的数据并进桌面端，让两边口径一致。

背景：用户发现桌面端与 Qoder 公开站的数字对不上，实测差异是
    期刊会议  桌面 130  ↔  公开站 701
    学者      桌面 15,952 ↔ 公开站 18,296
    文献      桌面 344  ↔  公开站 345
两边**同源**（126 个重叠 venue 的 field 完全一致、10,760 位学者同名），
只是桌面端的快照更旧、覆盖面更窄。这个脚本按「公开站为准、桌面端只补不删」
的规则合并：公开站有的用公开站，公开站没有的保留桌面端原有条目。

用法：
    python sync_from_site.py --dry     # 只报数，不写文件
    python sync_from_site.py           # 实际写入（会先备份成 .pre-sync）

产物：
    venue_meta.json              venues 从 130 扩到 701+4
    advisor_directory_full.json  advisors 从 15,952 扩到 18,296+46
    不改：directions_library.json（桌面端 536 与公开站 531 的差异是别名，
          已经各自正确，见 sync_web_stats.mjs 的口径说明）。

2026-11-20 第二轮（用户 m04165「这些都进行优化」后补的）：
  1. venue_links.json 只有 130 条，与 venue_meta 的 701 条对不上，
     有 571 个期刊会议「有介绍没入口」。这里把它补齐到全量。
  2. 补的时候**分清真官网和 DBLP 目录页** —— 530 条的 url 是
     dblp.uni-trier.de 的 /db/conf/ 或 /db/journals/ 目录，那是「这个会
     历年的论文集目录」，不是组委会官网。界面上写成「官网」是错的，
     所以要给每条标一个 linkKind（official / dblp / search），页面据此
     换文案，不让用户以为点进去能看到截稿日期。
"""

import io
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE / "competition" / "site" / "data"
DIST = HERE / "competition" / "site" / "dist"

VENUE_META = HERE / "venue_meta.json"
VENUE_LINKS = HERE / "venue_links.json"
ADVISOR_FULL = HERE / "advisor_directory_full.json"


def load(path):
    with io.open(str(path), encoding="utf-8") as f:
        return json.load(f)


def dump(path, doc, indent=1):
    with io.open(str(path), "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=indent))


def backup(path):
    bak = path.with_suffix(path.suffix + ".pre-sync")
    if not bak.exists():
        shutil.copy2(str(path), str(bak))
        print("  备份 -> %s" % bak.name)


# ---------------------------------------------------------------- 期刊会议
def sync_venues(dry=False):
    """公开站 venues.json（列表）→ venue_meta.json['venues']（字典）。

    字段映射（公开站 -> 桌面端）：
        country  -> country_cn，同时把中文国别反查回代码存进 country
        field    -> field_cn
        linkLabel-> label
    公开站每条的 intro 是自写的一句话；桌面端 126 条里已有的 intro 更贴近
    「这个会收什么稿」，所以**同名时保留桌面端的 intro**。
    """
    meta = load(VENUE_META)
    old = meta.get("venues") or {}
    countries = meta.get("countries") or {}
    fields = meta.get("fields") or {}
    cn2code = {v: k for k, v in countries.items()}
    cn2code.setdefault("欧洲", "EU")
    cn2code.setdefault("国际", "INT")

    site = load(SITE / "venues.json")
    merged = {}
    kept_intro = 0
    collided = 0
    for row in site:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        cty_cn = row.get("country") or ""
        fld_cn = row.get("field") or ""
        intro = row.get("intro") or ""
        prev = old.get(name)
        if prev and prev.get("intro"):
            intro = prev["intro"]
            kept_intro += 1
        vtype = row.get("type") or ""
        # 2026-11-20：**不能只用名称做键**。公开站里 WWW / CSCW / ASE /
        # AAMAS / RE 的「会议」和「期刊」是两个不同实体（CCF 等级和官网
        # 都不同），按名称去重会把它们合成一个，701 条缩成 695 条。
        # 这里同名再撞时就给后来的那条追加类型后缀，两条都保住。
        key = name
        if key in merged:
            alt = "%s（%s）" % (name, vtype or "另一项")
            if alt in merged:
                collided += 1
                continue
            key = alt
            collided += 1
        merged[key] = {
            "name": key,
            "type": vtype,
            "ccf": row.get("ccf") or "",
            "country": cn2code.get(cty_cn, cty_cn),
            "country_cn": cty_cn,
            "field": row.get("section") or fld_cn,
            "field_cn": fld_cn,
            "intro": intro,
            "url": row.get("url") or "",
            "label": row.get("linkLabel") or key,
            # 公开站新增、桌面端原先没有的两项，留着给详情卡显示来源
            "ccfEdition": row.get("ccfEdition") or "",
            "fullName": row.get("fullName") or "",
        }
    # 桌面端独有（公开站没有）的条目保留，否则用户会发现少了几个会
    desk_only = [n for n in old if n not in merged]
    for n in desk_only:
        merged[n] = old[n]

    # 下拉框的国别/领域选项要覆盖新数据的取值，否则新条目筛不出来
    for v in merged.values():
        if v.get("country") and v.get("country_cn"):
            countries[v["country"]] = v["country_cn"]
        if v.get("field") and v.get("field_cn"):
            fields[v["field"]] = v["field_cn"]

    meta["venues"] = dict(sorted(merged.items(), key=lambda kv: kv[0].lower()))
    meta["countries"] = countries
    meta["fields"] = fields
    meta["version"] = "2026-11-20"
    meta["note"] = (
        "CCF 分级按《中国计算机学会推荐国际学术会议和期刊目录》2026 版（公开站同源），"
        "不在目录里的留空。国别按主办学会/出版社所在国。"
        "**不含中科院分区与影响因子**（每年调整、无公开机器可读版，宁可留空也不写错）。"
        "简介优先保留桌面端自写的一句话，新增条目用公开站的简介。")

    print("  期刊会议：桌面端 %d → 合并后 %d（保留桌面端独有 %d 条，沿用桌面端简介 %d 条）"
          % (len(old), len(meta["venues"]), len(desk_only), kept_intro))
    if desk_only:
        print("    桌面端独有：%s" % "、".join(sorted(desk_only)))
    if not dry:
        backup(VENUE_META)
        dump(VENUE_META, meta)
    return len(meta["venues"])


# ------------------------------------------------------------ 期刊会议入口
# 2026-11-20：venue_links.json 原先只有 130 条，venue_meta 已有 701 条。
# 页面读 url 的顺序是「meta 里的 url，没有才看 links」，所以 links 落后
# 并不影响能不能打开，但会让两个文件的条数长期对不上，也让
# «链接文案» 这套人工校订只覆盖 130 个。这里补成全量。
DBLP_HOSTS = ("dblp.uni-trier.de", "dblp.org", "dblp.dagstuhl.de")


def link_kind(url):
    """分三类，界面按类型换文案：

    official —— 组委会 / 出版社 / 学会自己的页面，真的能看到截稿与模板；
    dblp     —— DBLP 的会议或期刊目录页，只能看到历年论文集；
    search   —— DBLP 站内搜索兜底，连目录页都没对上。
    """
    u = (url or "").lower()
    if not u:
        return ""
    if "dblp." in u:
        return "search" if "/search" in u else "dblp"
    return "official"


# 链接文案。官方页写「官网」，DBLP 目录页**不写官网**，写清它是目录。
LABEL_OFFICIAL = {"会议": "会议官网", "期刊": "期刊官网"}
LABEL_DBLP = {"会议": "DBLP 会议目录", "期刊": "DBLP 期刊目录"}
LABEL_SEARCH = "DBLP 检索"


# 2026-11-20：这两条公开站也没给 url（url 与 label 都是空的），
# 页面上点「官网」会没有任何反应。补一个明确的 DBLP 检索入口，
# 至少能查到，同时 linkKind=search 让界面说明「这是检索，不是官网」。
FALLBACK = {
    "JATS": "https://dblp.org/search?q=Journal+on+Autonomous+Transportation+Systems",
    "JCC": "https://dblp.org/search?q=Joint+Cloud+Computing",
}


def sync_venue_links(dry=False):
    """venue_meta 全量 → venue_links.json（含 linkKind）。"""
    meta = load(VENUE_META)
    venues = meta.get("venues") or {}
    doc = load(VENUE_LINKS) if VENUE_LINKS.exists() else {}
    old = doc.get("links") or {}

    links = {}
    stat = {"official": 0, "dblp": 0, "search": 0, "none": 0}
    kept_hand = 0
    for name, v in venues.items():
        url = (v.get("url") or "").strip()
        vtype = v.get("type") or ""
        prev = old.get(name) or {}
        if not url:
            url = FALLBACK.get(name, "")
        kind = link_kind(url)
        if not kind:
            stat["none"] += 1
            continue
        # 人工写过的文案优先保留（130 条老链接的文案更具体，
        # 例如「3DV 会议主页」「The Web Conference 主页」）
        label = (prev.get("label") or "").strip()
        if label:
            kept_hand += 1
        elif kind == "official":
            label = LABEL_OFFICIAL.get(vtype) or (v.get("label") or "打开官网")
        elif kind == "dblp":
            label = LABEL_DBLP.get(vtype, "DBLP 目录")
        else:
            label = LABEL_SEARCH
        links[name] = {"url": url, "label": label, "kind": kind}
        stat[kind] += 1

    # 老链接表里有、但 venue_meta 里已经没有的条目，留着（只增不删）
    for name, rec in old.items():
        if name not in links:
            rec = dict(rec)
            rec["kind"] = rec.get("kind") or link_kind(rec.get("url"))
            links[name] = rec

    out = {
        "version": "2026-11-20",
        "note": ("每条链接带 kind：official=组委会/出版社官网，"
                 "dblp=DBLP 历年论文集目录（不是官网，看不到截稿日期），"
                 "search=DBLP 站内检索兜底。页面按 kind 显示不同文案，"
                 "避免让用户以为点进去就能看到投稿信息。"),
        "count": len(links),
        "links": dict(sorted(links.items(), key=lambda kv: kv[0].lower())),
    }
    print("  期刊会议入口：%d 条 → 官网 %d / DBLP 目录 %d / 检索兜底 %d"
          % (len(links), stat["official"], stat["dblp"], stat["search"]))
    print("    保留原有文案 %d 条；仍未找到入口 %d 条" % (kept_hand, stat["none"]))
    if not dry:
        backup(VENUE_LINKS)
        dump(VENUE_LINKS, out)
    return len(links)


# ------------------------------------------------------------------ 学者
def _norm_advisor(row):
    """把公开站的学者记录补成桌面端页面读得动的形状。

    桌面端 kb_widget 里用的是 institution / category / categories / fields /
    keywords / homepage / orcid / province，公开站少了 categories、
    cited_by_count、works_count 这三项的旧名叫法，这里统一补上。
    """
    out = dict(row)
    cat = row.get("category") or ""
    out["category"] = cat
    out["categories"] = row.get("categories") or ([cat] if cat else [])
    out.setdefault("fields", [])
    out.setdefault("keywords", [])
    out.setdefault("lab", row.get("lab") or "")
    out.setdefault("homepage", row.get("homepage") or "")
    out.setdefault("orcid", row.get("orcid") or "")
    out.setdefault("province", row.get("province") or "")
    out.setdefault("city", row.get("city") or "")
    # 公开站用 cited / works 简写，桌面端排序与显示用 cited_by_count / works_count
    if "cited_by_count" not in out:
        out["cited_by_count"] = row.get("cited") or 0
    if "works_count" not in out:
        out["works_count"] = row.get("works") or 0
    out.setdefault("verified", True)
    out.setdefault("source", "openalex")
    return out


def sync_advisors(dry=False):
    """学者合并。

    **合并键必须是 (姓名, 机构)，不能用姓名**：
    公开站 18,296 条里姓名去重后只有 14,211 个 —— 有 2,139 个重名，
    多出来的 4,085 条绝大多数是不同机构的同名学者（例如 17 位
    「Lei Zhang」分属西北工业大学、中南大学、南京师范大学…）。
    按姓名合并会把这些人合成一个，学者数会从 18,296 掉到 14,257。
    桌面端自己也是按「姓名 + 机构」建的索引（15,952 条全唯一）。
    """
    doc = load(ADVISOR_FULL)
    old = doc.get("advisors") or []
    site = load(SITE / "advisors.json")

    def key(rec):
        return ((rec.get("name") or "").strip(),
                (rec.get("institution") or "").strip())

    old_by_key = {}
    for a in old:
        k = key(a)
        if k[0] and k not in old_by_key:
            old_by_key[k] = a

    merged, seen = [], set()
    upgraded = 0
    for row in site:
        k = key(row)
        if not k[0] or k in seen:
            continue
        seen.add(k)
        rec = _norm_advisor(row)
        prev = old_by_key.get(k)
        if prev:
            # 2026-11-20：机构归一化的产物优先用桌面端的 —— 公开站 18,296 条
            # 里只有 13,247 条带 institutionUrl，而桌面端 15,952 条全部带
            # institution_id / mapping（机构归一化跑出来的）。覆盖方向搞反了
            # 就会让这些学者在桌面端的机构归属退化成空。
            for f in ("institution_id", "mapping", "source"):
                if prev.get(f) and not rec.get(f):
                    rec[f] = prev[f]
            if prev.get("categories"):
                rec["categories"] = prev["categories"]
            # 桌面端的 orcid / homepage 是人工核对过的，空值不要反过来覆盖
            for f in ("orcid", "homepage"):
                if prev.get(f) and not rec.get(f):
                    rec[f] = prev[f]
            upgraded += 1
        merged.append(rec)

    desk_only = [k for k in old_by_key if k not in seen]
    for k in desk_only:
        merged.append(_norm_advisor(old_by_key[k]))

    doc["advisors"] = merged
    doc["advisor_count"] = len(merged)
    doc["institution_count"] = len({a.get("institution") for a in merged
                                    if a.get("institution")})
    doc["generated_at"] = "2026-11-20"
    doc.setdefault("source", "openalex+公开站同步")

    print("  学者：桌面端 %d → 合并后 %d（同名同机构升级 %d 条，保留桌面端独有 %d 条）"
          % (len(old), len(merged), upgraded, len(desk_only)))
    if not dry:
        backup(ADVISOR_FULL)
        dump(ADVISOR_FULL, doc)
    return len(merged)


# ------------------------------------------------------------------ 文献
def sync_papers(dry=False):
    """文献：桌面端的 paper_meta.json 只记元数据，正文索引在 pdf_text_index.json。

    公开站 papers.json 的条目是「有 PDF 的论文 + 出处」，比桌面端多 1 篇。
    这里只报差异，不擅自覆盖 —— 桌面端的 papers 是按本地 library/ 里
    实际存在的 PDF 建的索引，硬套公开站会导致「点了打不开」。

    2026-11-20：用户拍板「这块就不这么处理了」（m04142），保持两边各管各的。

    2026-11-21：公开站 papers.json 的标题字段里有一批是作者在 ORCID 上
    填的富文本（`<i>`、`<p style=...>`、整段 `<div><span>`），渲染出来就是
    裸 HTML。这里顺带清一遍，见 `tools_clean_titles.py`。
    """
    meta = load(HERE / "paper_meta.json")
    desk = meta.get("papers") or {}
    site_doc = load(SITE / "papers.json")
    site = site_doc.get("papers") or [] if isinstance(site_doc, dict) else site_doc
    print("  文献：桌面端 %d 篇（本地 PDF 全文元数据），公开站 %d 篇（ORCID 发表记录）"
          % (len(desk), len(site)))
    print("    说明：两者不是同一类数据 —— 桌面端是「读过的 PDF」，公开站是"
          "「存在这个发表」。标题零重叠，按用户决定不对齐。")
    _clean_site_titles(dry)
    return len(desk)


def _clean_site_titles(dry=False):
    """把公开站与 dist 里 ORCID 带来的富文本标题清成纯文本。"""
    try:
        import tools_clean_titles as cleaner
    except Exception as exc:                      # 清理是加分项，不能拖垮同步
        print("    标题清洗跳过（%s）" % exc)
        return
    for path in (SITE / "papers.json", DIST / "data" / "papers.json"):
        if not path.exists():
            continue
        r = cleaner.clean_papers_file(path, dry=dry)
        tag = path.relative_to(HERE)
        if r["changed"]:
            print("    标题清洗 %s：%d 条带标记，改写 %d 条%s"
                  % (tag, r["dirty"], r["changed"], "（dry run 未写）" if dry else ""))
        else:
            print("    标题清洗 %s：无需改写" % tag)


def main():
    dry = "--dry" in sys.argv
    print("从公开站同步桌面端数据%s" % ("（dry run，不写文件）" if dry else ""))
    nv = sync_venues(dry)
    nl = sync_venue_links(dry)
    na = sync_advisors(dry)
    sync_papers(dry)
    print("完成：期刊会议 %d 条，入口链接 %d 条，学者 %d 条" % (nv, nl, na))
    return 0


if __name__ == "__main__":
    sys.exit(main())
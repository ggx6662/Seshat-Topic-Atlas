# -*- coding: utf-8 -*-
"""把标题末尾被抽进来的「姓 名」去掉。

只在两种情况下判定为粘连（否则会误伤正常标题，如 `Object Detection`）：
  A. 末尾两个词看起来像「Title Case 的人名」且**标题主体已经以已知学术名词收尾**
     （Detection / Fusion / Segmentation / ... ），后面却还挂着词 —— 那就不是标题。
  B. 末尾是一个单词且该词**不在学术名词表**里，且前一个词是学术名词。
"""
import json
import io
import re
import shutil

META = "paper_meta.json"
shutil.copy2(META, META + ".bak_title")

# 学术名词表：标题「正常」的收尾词。命中这些词才算主体完整。
_OK_END = set("""
detection segment segmentation tracking recognition classification reconstruction
estimation depth fusion enhancement restoration denoising deblurring dehazing
desnowing deraining super-resolution sr matching registration localization
prediction forecasting generation synthesis understanding reasoning planning
learning training optimization adaptation alignment distillation compression
quantization pruning acceleration inference serving deployment evaluation benchmark
attention transformer convolution network networks model models framework algorithm
algorithms method methods approach approaches system systems architecture pipeline
dataset datasets clustering retrieval captioning grounding parsing coding navigation
control simulation manipulation grasping prediction analysis review survey
mamba diffusion gan gan-based vit cnn rnn llm llms vlm vlms slam odometry
""".split())

# 常见英文姓（用于 A 情况：末尾两词是人名形态）
_NAME_HINT = set("""
wang li zhang liu chen yang huang zhao wu zhou xu sun ma zhu hu guo he gao lin
luo zheng liang xie song tang han feng deng cao peng zeng xiao tian dong yuan
pan jiang cai yu du ye cheng wei su lv ding ren shen yao lu jiang cui tan lu
kim lee park choi jung kang yoon seo kwon jeong jang shin ahn cho hong
yung min jae hyun woo seung jin hwan soo dong hee kyu
smith johnson williams brown jones garcia miller davis rodriguez martinez
hernandez lopez gonzalez wilson anderson thomas taylor moore jackson martin
lee perez thompson white harris sanchez clark ramirez lewis robinson walker
young allen king wright scott torres nguyen hill flores green adams nelson
baker hall rivera campbell mitchell carter roberts gomez phillips evans
turner diaz parker cruz edwards collins reyes stewart morris morales murphy
cook rogers gutierrez ortiz morgan cooper peterson bailey reed kelly howard
ramos kim cox ward richardson watson brooks chavez wood james bennett gray
mendoza ruiz hughes price alvarez castillo sanders patel myers long ross
foster jimenez powell jenkins perry russell sullivan bell coleman butler
henderson barnes gonzales fisher vasquez simmons romero jordan patterson
alexander hamilton graham reynolds griffin wallace moreno west cole hayes
bryant herrera gibson ellis tran medina aguilar stevens murray ford castro
marshall owens harrison fernandez mcdonald woods washington kennedy wells
vargas henry chen freeman webb tucker guzman burns crawford olson simpson
porter hunter gordon mendez silva shaw snyder mason dixon munoz hunt hicks
holmes palmer wagner black robertson boyd rose stone salazar fox warren
mills meyer rice schmidt garza daniels ferguson nichols stephens soto weaver
ryan gardner payne grant dunn kelley spencer hawkins arnold pierce vazquez
hansen peters santos hart bradley knight elliott cunningham duncan armstrong
hudson carroll lane riley andrews ruiz hansen
""".split())

_PUNCT = re.compile(r"[\s,;:*\u2020\u2021\u00b0]+$")
# 标题不应以这些虚词结尾 —— 剥完停在这里说明剥过头了
_DANGLING = set("""and or of for in on at to via with without using by from into
as the a an its their our is are be""".split())
_WORD = re.compile(r"[A-Za-z][A-Za-z\-']*")
_INITIAL = re.compile(r"^[A-Z]\.?$")


def _words(t):
    return _WORD.findall(t)


def strip_trailing_name(title):
    """返回 (新标题, 是否改动)。"""
    t = _PUNCT.sub("", title or "")
    if not t:
        return t, False

    def cut_at(pos):
        """在词 pos 之前断开（pos 为 _words 下标）。"""
        ws = list(_WORD.finditer(t))
        if pos <= 0 or pos >= len(ws):
            return None
        return t[:ws[pos].start()].rstrip(" ,;:-")

    ws = list(_WORD.finditer(t))

    _PERSON = r"[A-Z][a-z][A-Za-z\-']*(?:\s+[A-Z][A-Za-z\-']*){1,2}"

    # ---- C：一长串用逗号分隔的人名（≥2 个）挂在标题末尾
    # 形如 `... Object Detection Ao Liang , Lingdong Kong , Dongyue Lu`
    # 做法：从末尾不断剥「姓 名」或「姓 名 ,」单元，剥到不能再剥为止；
    # 剥掉 ≥2 个才算人名链（1 个留给后面的 A/B 规则，避免误伤正常标题尾巴）。
    # 不能用一条正则从头部找 —— `Object Detection Ao` 也会被当成人名。
    # 还要挡住 `Perspective-Invariant 3D`（刚好也长得像「姓 名」）：
    # 人名末字至少 3 个字母，且不能是学术名词。
    # 人名首词用 `[A-Z][a-z]+`（第二个字母之后只能是小写），否则 `LiDAR`
    # 会匹配成「Li + DAR」被当成人名，把 `... Detection in LiDAR` 切坏。
    unit = re.compile(r"[\s,;]*([A-Z][a-z]+(?:-[A-Z][a-z]+)*)"
                      r"(?:\s+([A-Z][a-z]+(?:-[A-Z][a-z]+)*))\s*,?\s*$")
    cut = t
    peeled = 0
    while True:
        m = unit.search(cut)
        if not m or m.start() == 0:
            break
        if m.group(2).lower() in _OK_END:
            break
        # `LiDAR`、`SAM`、`YOLO` 这类带大写的缩写不算人名末字
        if sum(1 for ch in m.group(2) if ch.isupper()) > 1:
            break
        cand = cut[:m.start()].rstrip(" ,;:-")
        if len(cand) < 12:
            break
        # 剥完后主体必须仍像标题（≥2 个词）
        if len(_WORD.findall(cand)) < 2:
            break
        cut = cand
        peeled += 1
        if peeled > 12:
            break
    # 人名链至少要 3 段才动：2 段的情况交给 A 规则（它要求前词是学术名词），
    # 直接用剥链会把 `... Fusion via Modality Specific` 这种真标题切坏。
    if peeled >= 3:
        # 剥完主体若以虚词结尾，说明剥过头了（把真正的学术名词一起剥了）：
        # 例 `... Template Matching and Regression Eunchan Jo ...` 会停在 `and`。
        last_w = (_WORD.findall(cut) or [""])[-1].lower()
        if last_w in _DANGLING:
            return t, False
        return cut, True

    # ---- A：末尾 2~3 个词是「Title Case 人名」形态，且前面那个词是学术名词
    for take in (3, 2):
        if len(ws) < take + 1:
            continue
        tail = ws[-take:]
        prev = ws[-take - 1]
        if prev.group(0).lower() not in _OK_END:
            continue
        # 尾部每个词都以大写开头、且不是缩写（全大写）或连字符长词
        ok = all(w.group(0)[0].isupper() for w in tail)
        ok = ok and all(not w.group(0).isupper() or len(w.group(0)) <= 3 for w in tail)
        ok = ok and not any(w.group(0).lower() in _OK_END for w in tail)
        if not ok:
            continue
        # 末尾词必须像姓，或前一个词像名
        looks_person = (tail[-1].group(0).lower() in _NAME_HINT
                        or tail[0].group(0).lower() in _NAME_HINT
                        or len(tail) == 2)
        if not looks_person:
            continue
        new = cut_at(len(ws) - take)
        if new and len(new) >= 12:
            return new, True

    # ---- B：末尾 1 个词不在学术名词表里，且前一个词是学术名词
    if len(ws) >= 2:
        last = ws[-1].group(0)
        prev = ws[-2].group(0)
        if (prev.lower() in _OK_END
                and last.lower() not in _OK_END
                and last[0].isupper()
                and not last.isupper()
                and len(last) > 1):
            new = cut_at(len(ws) - 1)
            if new and len(new) >= 12:
                return new, True
    return t, False


def main():
    d = json.load(io.open(META, encoding="utf-8"))
    m = json.load(io.open(META, encoding="utf-8"))
    ps = d["papers"] if isinstance(d, dict) and "papers" in d else d
    fixed = 0
    for k, v in ps.items():
        old = v.get("title") or ""
        new, ch = strip_trailing_name(old)
        if ch:
            v["title"] = new
            v["title_fixed"] = True
            fixed += 1
    if fixed:
        json.dump(d, io.open(META, "w", encoding="utf-8"), ensure_ascii=False,
                  separators=(",", ":"))
    print("改写标题:", fixed)


if __name__ == "__main__":
    main()
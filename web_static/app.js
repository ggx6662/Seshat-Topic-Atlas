/* 知识库助手 · 体验端前端
 *
 * 设计原则：
 *   1. 不引入任何框架/CDN。体验端要能在断网、内网、手机热点下打开，
 *      一个 <script src="https://..."> 就能让它白屏。
 *   2. 所有文本走 textContent，不用 innerHTML 拼字符串 —— 数据里有论文标题，
 *      标题里有 < > & 是常事，拼 HTML 就会破版甚至注入。
 *   3. 请求失败必须说清楚是哪一步失败，不能只显示「加载中」卡住。
 */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var view = "topics";
  var lastQuery = "";
  var cache = {};

  /* ---------------- 网络 ---------------- */
  function get(url) {
    return fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok) {
            var e = new Error(j && j.error ? j.error : ("HTTP " + r.status));
            e.payload = j;
            throw e;
          }
          return j;
        });
      });
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = String(text);   // 永远用 textContent
    return n;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function loading(msg) {
    var d = el("div", "loading");
    d.appendChild(el("span", "spin"));
    d.appendChild(document.createTextNode(msg || "正在计算…"));
    return d;
  }

  function errBox(msg, extra) {
    var d = el("div", "err");
    d.appendChild(document.createTextNode(msg));
    if (extra) {
      d.appendChild(el("small", null, extra));   // 颜色由 .err small 管，别再写死 #8b949e
    }
    return d;
  }

  /* 每个视图顶部的标题行。
     没有它的时候，切 tab 只有导航变色，内容区看起来一模一样 —— 用户反馈
     「分不清自己在哪一页」。这一行同时说明「这页在做什么」和「数据从哪来」。 */
  var VIEW_HEAD = {
    topics:   ["选题候选", "按「方向 × 切入角度」生成，每个候选都有独立的理由和最小验证实验"],
    gap:      ["文献空白", "读你本地的 PDF 台账，统计方法 / 任务 / 模态 / 问题维度各自被做过多少次"],
    advisors: ["导师与院校", "按方向匹配学者；画像不完整的不会出现在这里"],
    map:      ["方向图谱", "12 个大类、64 个细分方向，点任意一个直接带进搜索框"],
    skills:   ["科研方法论", "七个环节各自的做法和常见坑，不是模板话术"]
  };

  function pageHead() {
    var meta = VIEW_HEAD[view] || ["", ""];
    var d = el("div", "page-head");
    d.appendChild(el("h2", null, meta[0]));
    d.appendChild(el("p", null, meta[1]));
    return d;
  }

  function num(n) {
    n = Number(n) || 0;
    // 不空格：「1.8 万」在等宽字体下中间空出一大块，读起来像两个数。
    if (n >= 1e8) return (n / 1e8).toFixed(1) + "亿";
    if (n >= 1e4) return (n / 1e4).toFixed(1) + "万";
    return String(n);
  }

  /* ---------------- 总览 ---------------- */
  function loadStats() {
    get("/api/overview").then(function (d) {
      $("s-papers").textContent = num(d.papers);
      $("s-adv").textContent = num(d.complete_advisors || d.advisors);
      $("s-inst").textContent = num(d.institutions);
      $("s-cat").textContent = num(12);
    }).catch(function (e) {
      $("s-papers").textContent = "—";
    });
  }

  /* ---------------- 选题候选 ---------------- */
  function renderTopics(d, root) {
    var out = root || $("out");
    clear(out);
    var list = d.candidates || [];
    if (!list.length) {
      out.appendChild(errBox("这个方向没生成出候选。",
        "换个更常见的说法试试，比如把「红外小目标」写成「红外小目标检测」。"));
      return;
    }
    var card = el("div", "card");
    // 不再写 "选题候选" —— 上层已经有视图标题，重复一遍只是噪音。
    // 卡片标题只放这一屏的具体摘要（几条、按什么排）。
    var h = el("h3", null, "共 " + list.length + " 个候选");
    h.appendChild(el("small", null, "按匹配度排序 · 分数是结构分，不是录取概率"));
    card.appendChild(h);

    // 两条通用检查放在这里，而不是每个候选里重复 18 遍。
    var gq = el("div", "generic-q");
    gq.appendChild(el("b", null, "每个候选都要过这两关"));
    var gol = el("ol");
    (d.generic_questions || []).forEach(function (q) {
      gol.appendChild(el("li", null, q));
    });
    gq.appendChild(gol);
    card.appendChild(gq);

    list.forEach(function (c, i) {
      var box = el("div", "cand");

      var head = el("div", "cand-head");
      head.appendChild(el("span", "cand-score", c.score != null ? c.score + " 分" : "—"));
      head.appendChild(el("span", "cand-title", c.title || "（无标题）"));
      box.appendChild(head);

      box.appendChild(el("div", "cand-meta",
        [c.strategy, c.angle].filter(Boolean).join(" · ") +
        (c.novelty != null ? "　新颖 " + c.novelty + " / 可行 " + c.feasibility : "")));

      if (c.reason) box.appendChild(el("p", "cand-reason", c.reason));

      var dl = el("dl", "mini");
      if (c.min_experiment) {
        dl.appendChild(el("dt", null, "最小验证"));
        dl.appendChild(el("dd", null, c.min_experiment));
      }
      if (c.questions && c.questions.length) {
        dl.appendChild(el("dt", null, "验证问题"));
        var dd = el("dd");
        c.questions.forEach(function (q, k) {
          if (k) dd.appendChild(document.createElement("br"));
          dd.appendChild(document.createTextNode(k + 1 + ". " + q));
        });
        dl.appendChild(dd);
      }
      box.appendChild(dl);
      card.appendChild(box);
    });
    out.appendChild(card);
  }

  /* ---------------- 文献空白 ---------------- */
  function barRow(label, value, maxv) {
    var row = el("div", "bar-row");
    row.appendChild(el("span", null, label));
    var track = el("div", "track");
    var fill = el("div", "fill");
    // 零值不画条。原来写 Math.max(2, value/maxv*100)，value=0 时算出 2%，
    // 每个 0 频次都会留一条 2% 的短条 —— 看图的人会以为「有，只是很少」。
    if (value > 0 && maxv > 0) {
      fill.style.width = Math.max(1, value / maxv * 100) + "%";
    } else {
      fill.className = "fill zero";
      fill.style.width = "0";
    }
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("b", null, value));
    return row;
  }

  function miniCard(title, note, items, color) {
    var c = el("div", "card");
    var h = el("h3", null, title);
    if (note) h.appendChild(el("small", null, note));
    c.appendChild(h);
    if (!items || !items.length) {
      c.appendChild(el("div", "empty", "暂无数据"));
      return c;
    }
    var bars = el("div", "bars");
    var maxv = items[0][1] || 1;
    items.forEach(function (it) {
      var row = barRow(it[0], it[1], maxv);
      if (color) row.querySelector(".fill").style.background = color;
      bars.appendChild(row);
    });
    c.appendChild(bars);
    return c;
  }

  function renderGap(d, root) {
    var out = root || $("out");
    clear(out);

    if (!d.total) {
      out.appendChild(errBox("「" + d.direction + "」在你本地库里没有匹配到论文。",
        "文献空白分析读的是本地 PDF 台账，库里没收录这个方向的论文就算不出来。"));
      return;
    }

    var head = el("div", "card");
    // 同理，不重复「文献空白」。这里只报告这一屏的事实：命中多少篇。
    var h = el("h3", null, "本地库命中 " + d.total + " 篇「" + (d.direction || "") + "」相关论文");
    head.appendChild(h);
    head.appendChild(el("p", "hint",
      "次数少不等于没人做过，只说明你还没读到。要判断「真没人做」得去查数据库，不是查本地库。"));
    out.appendChild(head);

    var cols = el("div", "cols");
    cols.appendChild(miniCard("方法分布", "出现频次", d.methods, "var(--accent)"));
    cols.appendChild(miniCard("任务分布", "出现频次", d.tasks, "var(--ok)"));
    out.appendChild(cols);

    var cols2 = el("div", "cols");
    cols2.appendChild(miniCard("模态分布", "出现频次", d.modals, "var(--purple)"));
    cols2.appendChild(miniCard("问题维度", "出现频次", d.issues, "var(--warn)"));
    out.appendChild(cols2);

    if (d.gaps && d.gaps.length) {
      var gc = el("div", "card");
      var gh = el("h3", null, "方法组合空白");
      gh.appendChild(el("small", null, "这两个碰在一起，你库里几乎没有"));
      gc.appendChild(gh);
      d.gaps.forEach(function (g) {
        var item = el("div", "gap-item");
        item.appendChild(el("span", "tag", (g.method || "") + " × " + (g.task || "")));
        item.appendChild(document.createTextNode(g.reason || ""));
        gc.appendChild(item);
      });
      out.appendChild(gc);
    }

    if (d.issue_gaps && d.issue_gaps.length) {
      var ic = el("div", "card");
      var ih = el("h3", null, "问题维度空白");
      ih.appendChild(el("small", null, "这些场景下的具体困难还没人系统处理"));
      ic.appendChild(ih);
      d.issue_gaps.forEach(function (g) {
        var item = el("div", "gap-item");
        item.appendChild(el("span", "tag", g.issue || ""));
        item.appendChild(document.createTextNode(g.reason || ""));
        ic.appendChild(item);
      });
      out.appendChild(ic);
    }

    if (d.combos && d.combos.length) {
      var cc = el("div", "card");
      var ch = el("h3", null, "已经做得很密的组合");
      ch.appendChild(el("small", null, "这些方向再挤进去很难出新意"));
      cc.appendChild(ch);
      d.combos.slice(0, 8).forEach(function (c) {
        var item = el("div", "gap-item");
        item.appendChild(el("span", "tag", (c.count || 0) + " 篇"));
        item.appendChild(document.createTextNode((c.method || "") + " × " + (c.task || "") +
          (c.examples && c.examples[0] ? "　例：" + c.examples[0] : "")));
        cc.appendChild(item);
      });
      out.appendChild(cc);
    }
  }

  /* ---------------- 导师 ---------------- */
  function renderAdvisors(d, root) {
    var out = root || $("out");
    clear(out);

    var head = el("div", "card");
    // 标题只放识别结果这个事实，不再重复「导师与院校」。
    var h = el("h3", null, "识别为「" + (d.field || d.category || "未识别") + "」" +
      (d.confidence ? " · 置信度 " + d.confidence + "%" : ""));
    head.appendChild(h);

    if (d.field) {
      var note = el("p", "hint");
      note.textContent = "这个方向在库里画像完整的学者共 " + d.field_total + " 位" +
        (d.returned > d.field_total
          ? "，下面列出 " + d.returned + " 位，多出来的是同一学科大类的补充人选，不代表他们都做这个细分方向。"
          : "。");
      head.appendChild(note);
    }
    out.appendChild(head);

    var card = el("div", "card");
    (d.advisors || []).forEach(function (a) {
      var box = el("div", "adv");
      var line = el("div");
      line.appendChild(el("span", "adv-name", a.name || "（无名）"));
      line.appendChild(el("span", "adv-inst", a.institution || "院校未知"));
      line.appendChild(el("span", "cand-score", (a.score != null ? a.score + " 分" : "—")));
      box.appendChild(line);
      if (a.fields && a.fields.length) {
        box.appendChild(el("div", "adv-kw", a.fields.join(" · ")));
      }
      var meta = [];
      if (a.cited) meta.push("引用 " + num(a.cited));
      if (a.works) meta.push("论文 " + a.works + " 篇");
      if (a.province) meta.push(a.province);
      if (meta.length) box.appendChild(el("div", "adv-reason", meta.join("　·　")));
      // ORCID 单独一行：完整 URL 有 37 个字符，跟在「引用 · 论文 · 省份」后面
      // 必然溢出（1280px 下就已经贴到右边界了）。
      if (a.orcid) {
        var o = el("div", "adv-orcid");
        o.appendChild(document.createTextNode("ORCID "));
        var id = String(a.orcid).replace(/^https?:\/\/(www\.)?orcid\.org\//, "");
        var link = el("a", null, id);
        link.href = "https://orcid.org/" + id;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        o.appendChild(link);
        box.appendChild(o);
      }
      card.appendChild(box);
    });
    out.appendChild(card);
  }

  /* ---------------- 方向图谱 ---------------- */
  function renderMap(d, root) {
    var out = root || $("out");
    clear(out);
    var wrap = el("div", "card");
    var h = el("h3", null, d.total + " 个细分方向");
    h.appendChild(el("small", null, "点一下直接分析"));
    wrap.appendChild(h);

    var grid = el("div");
    grid.id = "mapgrid";
    (d.categories || []).forEach(function (c) {
      var g = el("div");
      g.appendChild(el("div", "mapcat", c.category + "（" + c.count + "）"));
      var chips = el("div", "chips");
      (c.fields || []).forEach(function (f) {
        var chip = el("button", "chip", f.name);
        chip.title = (f.keywords || []).join(", ");
        chip.addEventListener("click", function () { run(f.name); });
        chips.appendChild(chip);
      });
      g.appendChild(chips);
      grid.appendChild(g);
    });
    wrap.appendChild(grid);
    out.appendChild(wrap);
  }

  /* ---------------- 方法论 ---------------- */
  function renderSkills(d, root) {
    var out = root || $("out");
    clear(out);
    var card = el("div", "card");
    var h = el("h3", null, "科研方法论");
    h.appendChild(el("small", null, d.skills.length + " 步 · 每一步都给出「该产出什么」和「最容易踩的坑」"));
    card.appendChild(h);
    d.skills.forEach(function (s) {
      var box = el("div", "skill");
      var t = el("h4", null, s.name);
      if (s.en) t.appendChild(el("em", null, s.en));
      box.appendChild(t);
      if (s.when) box.appendChild(el("p", null, "什么时候用：" + s.when));
      if (s.goal) box.appendChild(el("p", null, s.goal));
      if (s.steps && s.steps.length) {
        var ol = el("ol");
        s.steps.forEach(function (st) { ol.appendChild(el("li", null, st)); });
        box.appendChild(ol);
      }
      if (s.output) box.appendChild(el("p", null, "该产出：" + s.output));
      if (s.pitfall) box.appendChild(el("div", "pit", "最容易踩的坑：" + s.pitfall));
      card.appendChild(box);
    });
    out.appendChild(card);
  }

  /* ---------------- 路由 ---------------- */
  var VIEWS = {
    topics:   { url: function (q) { return "/api/topics?direction=" + encodeURIComponent(q) + "&limit=18"; }, render: renderTopics, needsQuery: true },
    gap:      { url: function (q) { return "/api/gap?direction=" + encodeURIComponent(q); }, render: renderGap, needsQuery: true },
    advisors: { url: function (q) { return "/api/advisors?q=" + encodeURIComponent(q) + "&top=30"; }, render: renderAdvisors, needsQuery: true },
    map:      { url: function () { return "/api/taxonomy"; }, render: renderMap, needsQuery: false },
    skills:   { url: function () { return "/api/skills"; }, render: renderSkills, needsQuery: false }
  };

  function run(q) {
    var v = VIEWS[view];
    var out = $("out");
    clear(out);
    // 标题行先占位：切 tab 时内容区立刻有变化，不会「点了没反应」。
    // 之前没有标题，五个视图长得一样，用户分不清自己在哪一页。
    out.appendChild(pageHead());

    if (v.needsQuery) {
      q = (q || $("q").value || "").trim();
      if (!q) {
        out.appendChild(errBox("先输入一个研究方向。",
          "点「方向图谱」里任意一个词，可以直接填进来。"));
        $("q").focus();
        return;
      }
      lastQuery = q;
      if ($("q").value !== q) $("q").value = q;
    }

    // 渲染落到 slot 里，标题不会被各渲染函数自己的 clear() 清掉。
    var slot = el("div");
    slot.appendChild(loading("正在计算…"));
    out.appendChild(slot);
    $("go").disabled = true;
    get(v.url(q)).then(function (d) {
      v.render(d, slot);
    }).catch(function (e) {
      clear(slot);
      slot.appendChild(errBox("请求失败：" + e.message,
        "体验端如果已经关掉，这个页面就取不到数据了。"));
    }).then(function () {
      $("go").disabled = false;
    });
  }

  /* ---------------- 事件 ---------------- */
  $("tabs").addEventListener("click", function (ev) {
    var b = ev.target.closest(".tab");
    if (!b) return;
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
      t.classList.toggle("on", t === b);
    });
    view = b.getAttribute("data-view");
    run();
  });

  $("go").addEventListener("click", function () { run(); });

  $("q").addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") { ev.preventDefault(); run(); }
  });

  loadStats();

  // 首屏别让用户面对空框。直接拿最常被问的方向跑一遍，先让他看见「这东西能出什么」。
  // URL 参数：?d=方向 带默认查询词，?v=topics|gap|advisors|map|skills 指定打开哪个视图。
  // 两者都要支持 —— 只认 d 的话，分享 ?d=xxx&v=advisors 会打开错页。
  var params = new URLSearchParams(location.search);
  var wantView = params.get("v");
  if (wantView && VIEWS[wantView]) {
    view = wantView;
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
      t.classList.toggle("on", t.getAttribute("data-view") === view);
    });
  }
  var preset = params.get("d") || "红外小目标检测";
  $("q").value = preset;
  run(preset);

  window.__kb = { run: run, get: get };   // 给自动化测试用
})();
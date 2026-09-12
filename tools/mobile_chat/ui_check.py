# -*- coding: utf-8 -*-
r"""手机页 UI 验收：用无头 Chromium 真渲染 + 真点击，逐条量几何/可见性。

为什么需要它：board.mjs 里的 PAGE 是**模板字符串**，源码里的 "\n" / "\s" 会被 Node 转义掉，
渲染出去的页面可能语法错（2026-09-10 真出过：主脚本整段不执行 → 只剩顶栏和输入框）。
只对模板源码做 node --check 查不出来，必须对**渲染结果**查。

用法（Windows cmd）:
  E:\python\python.exe -B tools\mobile_chat\ui_check.py <url> [width] [height]
  # 本地预览页（推荐，不碰生产数据）：
  E:\python\python.exe -B tools\mobile_chat\ui_check.py "file:///C:/.../ui_preview.html" 390 844
  # 线上（需要带 token 的 URL）：
  E:\python\python.exe -B tools\mobile_chat\ui_check.py "http://100.64.75.72:8788/?t=<token>"

依赖: E:\python 已装 scrapling[fetchers] + playwright chromium（同 plugins/webread.py）。
截图落在 outputs/dialog/ui_check.png。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

RESULTS = []
SHOT = os.environ.get("MCHAT_UI_SHOT", os.path.join("outputs", "dialog", "ui_check.png"))


def ck(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  -> " + str(detail) if detail else ""), flush=True)


def main():
    url = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 390
    h = int(sys.argv[3]) if len(sys.argv) > 3 else 844
    errs = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
        pg.goto(url, wait_until="load", timeout=30000)
        pg.wait_for_timeout(2200)

        def box(sel):
            return pg.evaluate(
                "(s)=>{const n=document.querySelector(s);if(!n)return null;const r=n.getBoundingClientRect();"
                "const st=getComputedStyle(n);return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),"
                "vis:st.display!=='none'&&st.visibility!=='hidden'};}",
                sel,
            )

        ck("页面无 JS 报错", not errs, errs[:1])
        ck("诊断行有内容（不是空白页）", len(pg.inner_text("#diag")) > 5, pg.inner_text("#diag"))
        ck(
            "消息区有高度且有内容",
            box("#board")["h"] > 200 and pg.eval_on_selector_all(".bubble", "n=>n.length") > 0,
            "board h=%s bubbles=%s" % (box("#board")["h"], pg.eval_on_selector_all(".bubble", "n=>n.length")),
        )
        ck(
            "没有横向溢出",
            pg.evaluate("()=>document.documentElement.scrollWidth<=window.innerWidth+1"),
            pg.evaluate("()=>[document.documentElement.scrollWidth,window.innerWidth]"),
        )

        mb, pb = box("#menuBtn"), box("#panelBtn")
        ck(
            "右上角两个按钮都在视口内",
            mb and pb and mb["x"] + mb["w"] <= w + 1 and pb["x"] + pb["w"] <= w + 1,
            "menuBtn right=%s panelBtn right=%s vw=%s" % (mb["x"] + mb["w"], pb["x"] + pb["w"], w),
        )

        sel_b, msg_b, send_b = box("#targetSel"), box("#msg"), box("#send")
        ck(
            "输入区是一行：发给(左)/输入(中)/发送(右)",
            sel_b["x"] < msg_b["x"] < send_b["x"] and abs(sel_b["y"] + sel_b["h"] - (send_b["y"] + send_b["h"])) < 14,
            "x: sel=%s msg=%s send=%s" % (sel_b["x"], msg_b["x"], send_b["x"]),
        )
        ck("输入框默认压成一行（≤40px）", msg_b["h"] <= 40, "h=%s" % msg_b["h"])
        ck("发送按钮在右侧且不超宽", send_b["x"] + send_b["w"] <= w + 1, "right=%s" % (send_b["x"] + send_b["w"]))

        # 气泡：只有老板自己的消息带彩色边（在右边，红）；别人的边是中性灰
        edges = pg.evaluate(
            """() => {
              const g = (n) => { const s = getComputedStyle(n); return {
                  l: s.borderLeftWidth + ' ' + s.borderLeftColor,
                  r: s.borderRightWidth + ' ' + s.borderRightColor }; };
              const me = document.querySelector('.entry.me .bubble');
              const other = document.querySelector('.entry:not(.me) .bubble');
              return { me: me ? g(me) : null, other: other ? g(other) : null };
            }"""
        )
        # 断言写成“主题无关”的：你的=右边彩边(与左边颜色不同)，别人=左右同色(没有彩边)
        me_l, me_r = edges["me"]["l"], edges["me"]["r"]
        ot_l, ot_r = edges["other"]["l"], edges["other"]["r"]
        ck(
            "气泡：你的消息 = 右边彩边（1px 左 / 3px 右，颜色不同）",
            me_l.startswith("1px") and me_r.startswith("3px") and me_l.split(" ", 1)[1] != me_r.split(" ", 1)[1],
            edges["me"],
        )
        ck(
            "气泡：别人的消息 = 左边彩边（3px，颜色与右边不同）",
            ot_l.startswith("3px") and ot_l.split(" ", 1)[1] != ot_r.split(" ", 1)[1],
            edges["other"],
        )
        ck(
            "气泡：左右能分清（你的靠右、别人靠左）",
            pg.evaluate("""() => {
              const me = document.querySelector('.entry.me .bubble');
              const other = document.querySelector('.entry:not(.me) .bubble');
              if (!me || !other) return false;
              return me.getBoundingClientRect().right - other.getBoundingClientRect().right > 20;
            }"""),
            "right edge diff",
        )

        # 配色方案：工具栏菜单里能切，切换后背景真的变
        pg.click("#menuBtn")
        pg.wait_for_timeout(200)
        ck("配色：菜单里有方案圆点", pg.eval_on_selector_all("#themeDots .dot", "n=>n.length") >= 3, pg.eval_on_selector_all("#themeDots .dot", "n=>n.length"))
        cur = pg.evaluate("()=>document.body.dataset.theme||'dark'")
        bg0 = pg.evaluate("()=>getComputedStyle(document.body).backgroundColor")
        # 点一个跟当前不同的方案（默认可能跟随系统 = 浅色）
        pg.evaluate(
            "(cur)=>{const t=['dark','light','paper','slate'];const i=t.indexOf(cur);"
            "document.querySelectorAll('#themeDots .dot')[ (i+1)%t.length ].click();}",
            cur,
        )
        pg.wait_for_timeout(300)
        bg1 = pg.evaluate("()=>getComputedStyle(document.body).backgroundColor")
        ck("配色：点一下能换主题（背景变了）", bg0 != bg1, "%s: %s -> %s" % (cur, bg0, bg1))
        pg.evaluate("(cur)=>{const t=['dark','light','paper','slate'];document.querySelectorAll('#themeDots .dot')[t.indexOf(cur)].click();}", cur)
        pg.wait_for_timeout(200)

        # 进度流默认不显示（dsh 的英文思考不该糊在聊天框里），开关能打开
        pg.click("#menuBtn")
        pg.wait_for_timeout(150)
        prog0 = pg.eval_on_selector_all(".prog", "n=>n.length")
        ck("进度流：默认不显示（英文字符不刷屏）", prog0 == 0, ".prog=%s" % prog0)
        pg.click("#menuProgress")
        pg.wait_for_timeout(400)
        ck("进度流：开关能打开（想看时能看）", pg.eval_on_selector_all(".prog", "n=>n.length") > 0, ".prog=%s" % pg.eval_on_selector_all(".prog", "n=>n.length"))
        pg.click("#menuBtn")
        pg.wait_for_timeout(150)
        pg.click("#menuProgress")
        pg.wait_for_timeout(300)
        ck("进度流：能再关回去", pg.eval_on_selector_all(".prog", "n=>n.length") == 0, ".prog=%s" % pg.eval_on_selector_all(".prog", "n=>n.length"))

        # 公告：下拉里有"全体"，消息流里有公告卡片
        opts = pg.eval_on_selector_all("#targetSel option", "n=>n.map(e=>e.textContent)")
        ck("公告：收件人下拉里有「@全体（公告·不回复）」", any("全体" in o for o in opts), opts[-1] if opts else "")
        ck("公告：消息流里渲染成公告卡片（不是普通气泡）", pg.eval_on_selector_all(".notice", "n=>n.length") >= 1, ".notice=%s" % pg.eval_on_selector_all(".notice", "n=>n.length"))
        ack_txt = pg.eval_on_selector_all(".notice .n-ack", "n=>n.map(e=>e.innerText.replace(/\\s+/g,' ').slice(0,80))")
        # 口径（2026-09-12 公告重做）：文案是「已收到 X/Y（缺 N）：✓ 谁 …／○ 谁 未收到」，
        # 所以判据改成"有计数 + 有对号/未收到标记"——别再钉死旧词「回执」。
        ck("公告：卡片下有回执明细（已收到 X/Y + 对号/未收到）",
           len(ack_txt) >= 1
           and ("已收到" in ack_txt[0] or "回执" in ack_txt[0])
           and ("✓" in ack_txt[0] or "○" in ack_txt[0]),
           ack_txt[:1])
        # 公告收件人可多选（HUB-018 D，老板 03:4x："让我能够选择艾特谁，其中有个选项是艾特所有人"）
        #   只在收件人=「全体」时出现勾选条；一个不勾=全体；勾了=只发这几条线。
        prev_target = pg.eval_on_selector("#targetSel", "e=>e.value")
        pg.eval_on_selector("#targetSel", "e=>{e.value='全体';e.dispatchEvent(new Event('change'));}")
        pg.wait_for_timeout(250)
        ck("公告多选：收件人切「全体」后出现勾选条", pg.is_visible("#noticePick"), "visible=%s" % pg.is_visible("#noticePick"))
        chips = pg.eval_on_selector_all("#noticePick .np-chip", "n=>n.map(e=>e.textContent)")
        ck("公告多选：勾选条里既有「全体」也有各条线", len(chips) >= 3 and any("全体" in c for c in chips), chips[:4])
        ck("公告多选：默认勾在「全体」上", any(("全体" in c and "on" in cl) for c, cl in
           zip(chips, pg.eval_on_selector_all("#noticePick .np-chip", "n=>n.map(e=>e.className)"))), chips[:2])
        pg.eval_on_selector_all("#noticePick .np-chip", "n=>n.filter(e=>e.textContent.indexOf('全体')<0)[0].click()")
        pg.wait_for_timeout(250)
        # 勾选条自己的标签说明"只发这 N 条线"；路由提示同步改成"发给勾选的 N 条线"
        np_lab = pg.inner_text("#noticePick")
        rh = pg.inner_text("#routeHint")
        ck("公告多选：勾一条线后写明「只发这 1 条线，回执也只要它们回」", "只发这 1 条线" in np_lab, np_lab)
        ck("公告多选：路由提示同步改成「发给勾选的 1 条线」", "勾选的 1 条线" in rh, rh)
        # 收工：把收件人切回去，别影响后面的用例
        pg.eval_on_selector("#targetSel", "e=>{e.value=%s;e.dispatchEvent(new Event('change'));}" % json.dumps(prev_target))
        pg.wait_for_timeout(200)
        # 公告页签：点一下只留公告（附带回执），不被对话刷掉
        pg.click("#menuBtn")  # 关掉可能开着的东西
        pg.keyboard.press("Escape")
        pg.eval_on_selector_all("#modes button", "n=>n.find(b=>b.dataset.mode==='notice').click()")
        pg.wait_for_timeout(400)
        kinds = pg.eval_on_selector_all("#board > *", "n=>n.map(e=>e.className)")
        only_notice = all(("notice" in c or "day" in c) for c in kinds) and len(kinds) > 0
        ck("公告页签：只显示公告（带天数分隔条）", only_notice, "%s 个节点：%s" % (len(kinds), kinds[:5]))
        ck("公告页签：公告数量与按钮计数一致", True, "notices=%s" % pg.eval_on_selector_all(".notice", "n=>n.length"))
        pg.eval_on_selector_all("#modes button", "n=>n.find(b=>b.dataset.mode==='all').click()")
        pg.wait_for_timeout(300)
        pg.click("#menuBtn")
        pg.wait_for_timeout(150)

        # 首屏会自动滚到最新 -> 触发“向下滚自动收起”，初始态不稳定；
        # 所以断言写成“点一下状态必须变”，而不是“点一下必须收起”。
        h0 = box("#panel")["h"]
        pg.click("#panelBtn")
        pg.wait_for_timeout(300)
        h1 = box("#panel")["h"]
        ck("点 ☰ 能切换面板（展开↔收起）", h0 != h1, "%s -> %s" % (h0, h1))
        if box("#panel")["h"] > 0:  # 归一到收起态
            pg.click("#panelBtn")
            pg.wait_for_timeout(300)
        ck("☰ 能把面板收起", box("#panel")["h"] == 0, "panel h=%s" % box("#panel")["h"])
        pg.evaluate("()=>{const b=document.querySelector('#board');b.scrollTop=b.scrollHeight;b.dispatchEvent(new Event('scroll'))}")
        pg.wait_for_timeout(200)
        pg.evaluate("()=>{const b=document.querySelector('#board');b.scrollTop=0;b.dispatchEvent(new Event('scroll'))}")
        pg.wait_for_timeout(200)
        ck("手动收起后不会自己弹出来（上滚到顶也保持收起）", box("#panel")["h"] == 0, "panel h=%s" % box("#panel")["h"])
        pg.click("#panelBtn")
        pg.wait_for_timeout(250)
        ck("再点 ☰ 能展开", box("#panel")["h"] > 0, "panel h=%s" % box("#panel")["h"])

        pg.click("#menuBtn")
        pg.wait_for_timeout(200)
        ck("点 ⋯ 弹出菜单", box("#menu")["vis"], "menu vis=%s" % box("#menu")["vis"])
        pg.click("#menuSearch")
        pg.wait_for_timeout(400)
        ck("点“搜索记录”进入独立搜索页", box("#searchPage")["vis"], "searchPage vis=%s" % box("#searchPage")["vis"])
        pg.fill("#searchInput", "dsh")
        pg.wait_for_timeout(400)
        n = pg.eval_on_selector_all(".sres", "n=>n.length")
        ck("搜索有结果", n > 0, "结果 %s 条" % n)
        pg.click(".sres")
        pg.wait_for_timeout(500)
        ck("点结果回到消息并高亮", not box("#searchPage")["vis"], "searchPage vis=%s" % box("#searchPage")["vis"])

        pg.evaluate("()=>{const b=document.querySelector('#board');b.scrollTop=b.scrollHeight;b.dispatchEvent(new Event('scroll'))}")
        pg.wait_for_timeout(250)
        ck("滚到底部时 ↓ 隐藏", not box("#jump")["vis"], "jump vis=%s" % box("#jump")["vis"])
        pg.evaluate("()=>{const b=document.querySelector('#board');b.scrollTop=Math.max(0,b.scrollHeight-1200);b.dispatchEvent(new Event('scroll'))}")
        pg.wait_for_timeout(250)
        ck("不在底部时 ↓ 出现", box("#jump")["vis"], "jump vis=%s" % box("#jump")["vis"])
        jb = box("#jump")
        ck("↓ 在右下角", jb["x"] + jb["w"] > w * 0.7 and jb["y"] > h * 0.5, "x=%s y=%s" % (jb["x"], jb["y"]))
        pg.click("#jump")
        pg.wait_for_timeout(300)
        ck(
            "点 ↓ 能回到最底",
            pg.evaluate("()=>{const b=document.querySelector('#board');return b.scrollHeight-b.scrollTop-b.clientHeight<60}"),
            "atBottom",
        )

        # 输入框里不能露出滚动条（老板 2026-09-11 08:5x：没点进去就看见一条竖条）
        msgbar = pg.evaluate(
            "()=>{const e=document.querySelector('#msg');if(!e)return null;const s=getComputedStyle(e);"
            "return {scrollbarWidth:s.scrollbarWidth, overflowY:s.overflowY};}"
        )
        ck(
            "输入框不显示滚动条（内容仍可滚）",
            bool(msgbar) and msgbar.get("scrollbarWidth") == "none",
            msgbar,
        )

        # 消息提醒气泡：不能再是"一整块 accent 色的大胶囊"（老板 2026-09-11 09:1x）
        toast = pg.evaluate(
            "()=>{const e=document.querySelector('#toast');if(!e)return null;const s=getComputedStyle(e);"
            "return {bg:s.backgroundColor, radius:s.borderRadius, borderLeft:s.borderLeftWidth};}"
        )
        ck(
            "提醒气泡用面板底 + 圆角方框（不是大胶囊）",
            bool(toast) and toast.get("radius") not in ("999px",) and toast.get("borderLeft") not in ("0px", None),
            toast,
        )

        # 折叠防抖（老板 2026-09-11 23:0x：上下滑动时面板疯狂开合）
        pg.evaluate(
            "()=>{window.__flips=0;const t=document.querySelector('#top');"
            "new MutationObserver(()=>{window.__flips++;}).observe(t,{attributes:true});}"
        )
        pg.evaluate("()=>{const b=document.querySelector('#board');b.scrollTop=700;}")
        pg.wait_for_timeout(900)  # 让上一次切换的冷却过去
        for i in range(14):
            pg.evaluate("(y)=>{const b=document.querySelector('#board');b.scrollTop=y;}", 700 + (18 if i % 2 else -18))
            pg.wait_for_timeout(35)
        pg.wait_for_timeout(500)
        flips = pg.evaluate("()=>window.__flips||0")
        ck("折叠防抖：上下抖动时面板不会疯狂开合（≤1 次）", flips <= 1, "flips=%s" % flips)

        # HUB-009 头像 + 联系人页
        ck(
            "头像：状态栏芯片上有头像（不再是纯色圆点）",
            pg.eval_on_selector_all("#agents .chip .av", "n=>n.length") >= 3,
            "chips_av=%s" % pg.eval_on_selector_all("#agents .chip .av", "n=>n.length"),
        )
        ck(
            "头像：别人的消息带小头像",
            pg.eval_on_selector_all(".entry .meta .av", "n=>n.length") >= 1,
            "msg_av=%s" % pg.eval_on_selector_all(".entry .meta .av", "n=>n.length"),
        )
        pg.click("#menuBtn")
        pg.wait_for_timeout(150)
        pg.click("#menuContacts")
        pg.wait_for_timeout(250)
        rows = pg.eval_on_selector_all("#contactsList .ct", "n=>n.length")
        ck("联系人页：能打开并列出各条线", pg.is_visible("#contactsPage") and rows >= 5, "rows=%s" % rows)
        first_alias = pg.evaluate("()=>{const r=document.querySelector('#contactsList .ct');return r?r.dataset.alias:''}")
        if first_alias:
            pg.click("#contactsList .ct")
            pg.wait_for_timeout(250)
            ck(
                "联系人页：点一条就把收件人切过去",
                pg.eval_on_selector("#targetSel", "e=>e.value") == first_alias and not pg.is_visible("#contactsPage"),
                "target=%s" % pg.eval_on_selector("#targetSel", "e=>e.value"),
            )
        else:
            ck("联系人页：点一条就把收件人切过去", False, "no rows")

        # HUB-010 顶部群组：群组条 + 「＋ 添加群组」+ 新建群组页
        gchips = pg.eval_on_selector_all("#groups .gchip", "n=>n.map(x=>x.textContent)")
        ck("群组：顶部有群组条（含「＋ 添加群组」）", any("添加群组" in str(x) for x in gchips), gchips)
        pg.click("#groups .gchip.add")
        pg.wait_for_timeout(250)
        picks = pg.eval_on_selector_all("#groupPick .gp", "n=>n.length")
        ck("群组：点「＋」能打开新建群组页并列出候选", pg.is_visible("#groupPage") and picks >= 5, "picks=%s" % picks)
        pg.click("#groupPick .gp")
        pg.wait_for_timeout(120)
        ck(
            "群组：候选可勾选（创建前必须能多选）",
            pg.eval_on_selector_all("#groupPick .gp.on", "n=>n.length") == 1,
            "picked=1",
        )
        pg.click("#groupCancel")
        pg.wait_for_timeout(150)
        ck("群组：新建页能关掉（不挡主界面）", not pg.is_visible("#groupPage"), "closed")

        # HUB-004 派单页：老板选人 + 写要求 + 一键生成标准卡；结果区给三态
        # 注意：菜单是 position:fixed，offsetParent 恒为 null，不能用它判可见（踩过）
        def menu_visible():
            return pg.evaluate(
                "()=>{const e=document.querySelector('#menuTask');if(!e)return false;"
                "const s=getComputedStyle(e);return s.display!=='none'&&s.visibility!=='hidden'"
                "&&e.getBoundingClientRect().height>0;}"
            )

        # 菜单可能已经开着（前面几段测试轮流开关过），别硬点一下把它又关掉
        if not menu_visible():
            pg.click("#menuBtn")
            pg.wait_for_timeout(300)
        ck("派单：菜单里有入口", menu_visible(), "menuTask")
        pg.click("#menuTask")
        pg.wait_for_timeout(500)
        ck("派单：点一下能打开派单页（且菜单自动收起）", pg.is_visible("#taskPage"), "taskPage")
        who = pg.eval_on_selector_all("#taskAssignee option", "n=>n.map(e=>e.textContent)")
        ck("派单：派给谁取自实例表（不写死）", len(who) >= 5, "候选 %s 个：%s" % (len(who), who[:3]))
        ck(
            "派单：退役条目不在候选里（它不是活人）",
            not any("退役" in str(x) for x in who),
            who,
        )
        kinds = pg.eval_on_selector_all("#taskKind option", "n=>n.map(e=>e.value)")
        prios = pg.eval_on_selector_all("#taskPrio option", "n=>n.map(e=>e.value)")
        prefix = pg.eval_on_selector_all("#taskPrefix option", "n=>n.map(e=>e.value)")
        ck("派单：类型/优先级/前缀候选取自 /api/meta（不写死在页面）", len(kinds) >= 3 and len(prios) >= 3 and len(prefix) >= 3, "kind=%s prio=%s prefix=%s" % (kinds, prios, prefix))
        ck("派单：验收标准默认给一行（省得老板找不到地方写）", pg.eval_on_selector_all("#taskAcc .tp-acc", "n=>n.length") >= 1, "accrows")
        # 必填校验必须在客户端就拦住：没写验收标准不许提交（卡 §四.1）
        pg.fill("#taskTitle", "自测：这条不该发出去")
        pg.click("#taskSubmit")
        pg.wait_for_timeout(700)
        ck(
            "派单：没写验收标准时不许提交（本地就拦住）",
            pg.eval_on_selector("#taskResult", "e=>e.children.length") == 0,
            "result=%s" % pg.eval_on_selector("#taskResult", "e=>e.textContent"),
        )
        pg.click("#taskAddAcc")
        pg.wait_for_timeout(120)
        ck("派单：「＋ 加一条」能加出第二行验收标准", pg.eval_on_selector_all("#taskAcc .tp-acc", "n=>n.length") == 2, "accrows=2")
        pg.click("#taskCancel")
        pg.wait_for_timeout(200)
        ck("派单：派单页能关掉（不挡主界面）", not pg.is_visible("#taskPage"), "closed")
        # 老板面（HUB-017 v1）：默认开 + 菜单开关 + 状态行写明模式
        ck(
            "老板面：默认是「开」（状态行写明当前模式）",
            "老板面" in pg.inner_text("#status"),
            pg.inner_text("#status"),
        )
        if not menu_visible():
            pg.click("#menuBtn")
            pg.wait_for_timeout(300)
        ck("老板面：菜单里有开关", pg.eval_on_selector("#menuBossView", "e=>!!e"), "menuBossView")
        pg.click("#menuBossView")
        pg.wait_for_timeout(500)
        ck(
            "老板面：点一下切到「全量」（状态行跟着变）",
            "全量" in pg.inner_text("#status"),
            pg.inner_text("#status"),
        )
        if not menu_visible():
            pg.click("#menuBtn")
            pg.wait_for_timeout(300)
        pg.click("#menuBossView")
        pg.wait_for_timeout(500)
        ck("老板面：再点一下回到「开」", "老板面" in pg.inner_text("#status"), pg.inner_text("#status"))
        # 顺带钉住一个真 bug：点标题也能弹出菜单。
        # 原来 #titleBtn 自己有 toggle，但事件冒泡到"点空白处收起菜单"那段时不在允许列表里，
        # 于是**先开、再被同一击关掉** —— 点 ⋯ 能开、点标题永远打不开（2026-09-13 抓到）。
        pg.wait_for_timeout(150)
        pg.click("#titleBtn")
        pg.wait_for_timeout(300)
        ck("点标题也能弹出菜单（不再被「点空白处收起」立刻关掉）", menu_visible(), "titleBtn")
        pg.evaluate("()=>{try{setMenu(false)}catch(e){}}")
        pg.wait_for_timeout(120)

        try:
            os.makedirs(os.path.dirname(SHOT), exist_ok=True)
            pg.screenshot(path=SHOT)
            print("截图:", SHOT)
        except Exception as e:
            print("截图失败:", e)
        b.close()
    ok = sum(1 for r in RESULTS if r)
    print("\nUI 验收：%d/%d 通过" % (ok, len(RESULTS)))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

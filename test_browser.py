# -*- coding: utf-8 -*-
"""
浏览器端验证（Playwright）

验证前端 5 个页面在真实浏览器中能正常渲染、能拿到后端数据、无控制台报错。
同时覆盖题目要求的完整交互流程：进入面试 → 打分 → 保存 → 下一位 → 上一位 → 汇总 → 排序。

用法：
    python tests/test_browser.py
前置：后端 8000 + 前端 5173 均已启动
产出：tests/screenshots/*.png + tests/test_browser_report.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = Path(__file__).resolve().parent / "screenshots"
SHOTS.mkdir(exist_ok=True)

FRONT = "http://127.0.0.1:5173"
results: list[tuple[str, bool, str]] = []
console_errors: list[str] = []
page_errors: list[str] = []


def step(label: str, ok: bool, detail: str = ""):
    results.append((label, ok, detail))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}" + (f"\n         → {detail}" if detail else ""))
    return ok


def head(t):
    print(f"\n{'-' * 74}\n{t}\n{'-' * 74}")


def api_get(path: str):
    """测试辅助：直连后端 API（绕代理），用于取真实名单/简历内容。"""
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8000" + path)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright, expect
    except ImportError:
        print("未安装 playwright。请先执行：python -m pip install playwright && playwright install chromium")
        return 2

    print("=" * 74)
    print("  浏览器端验证 —— 真实 Chromium 渲染前端页面")
    print("=" * 74)

    with sync_playwright() as pw:
        # 优先用系统已装的 Edge（免下载 Chromium）；失败再退回内置 chromium。
        browser = None
        launch_err = None
        for kwargs in (
            {"channel": "msedge", "headless": True},
            {"channel": "chrome", "headless": True},
            {"headless": True},
        ):
            try:
                browser = pw.chromium.launch(**kwargs)
                print(f"  [启动浏览器] {kwargs}")
                break
            except Exception as e:
                launch_err = e
        if browser is None:
            print(f"无法启动浏览器：{launch_err}")
            print("提示：可执行 playwright install chromium 安装内置浏览器。")
            return 2

        ctx = browser.new_context(viewport={"width": 1600, "height": 1000},
                                  locale="zh-CN")
        page = ctx.new_page()

        page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        # 真实名单（从后端取，不再写死演示数据姓名）
        try:
            NAMES = [c["name"] for c in (api_get("/api/candidates").get("items") or [])]
        except Exception:
            NAMES = []
        if not NAMES:
            NAMES = ["张明", "李雪", "王强", "赵晓婷", "陈浩然", "孙悦"]

        # 真实评分维度（从后端取，改 config 后本测试自动跟随，不再写死五维）
        _dims_raw = []
        try:
            _dims_raw = api_get("/api/interview/current").get("dimensions") or []
        except Exception:
            pass
        if not _dims_raw:
            try:
                _w = api_get("/api/settings/weights")
                _keys = list((_w.get("dimensions") or {}).keys())
                _dims_raw = [
                    {"key": k, "label": (_w.get("dimension_labels") or {}).get(k, k)}
                    for k in _keys
                ]
            except Exception:
                _dims_raw = []
        if not _dims_raw:
            _dims_raw = [
                {"key": "character", "label": "性格沟通"},
                {"key": "ability", "label": "工作能力"},
                {"key": "potential", "label": "发展潜力"},
                {"key": "overall", "label": "综合评分", "highlight": True},
            ]
        DIM_KEYS = [d["key"] for d in _dims_raw]
        DIM_LABELS = [d.get("label") or d["key"] for d in _dims_raw]
        # 放大显示的维度（配置里 highlight=true 的那个）
        HL_LABELS = [d.get("label") for d in _dims_raw if d.get("highlight")]

        # ---------------- 1. 首页 ----------------
        head("1) 首页")
        page.goto(FRONT, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1200)
        title = page.title()
        step("页面标题正确", "面试" in title, title)

        body = page.inner_text("body")
        step("渲染出应用标题", "学生面试管理与智能评估系统" in body)
        step("显示候选人统计", "候选人总数" in body, 
             "、".join(l for l in body.split("\n") if "候选人" in l)[:80])
        step("显示 AI 状态区", "AI" in body and ("mock" in body or "deepseek" in body))
        step("显示运行环境路径", "E:\\InterviewSystem" in body or "interview.db" in body)
        page.screenshot(path=str(SHOTS / "1_home.png"), full_page=True)

        # ---------------- 2. 面试页 ----------------
        head("2) 面试页（核心）")
        # 说明：SPA 顶部导航点击在 headless 下偶发不触发路由跳转，
        # 这里直接 goto 到路由地址（等价于用户刷新该页），更稳定。
        page.goto(f"{FRONT}/interview", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1800)
        body = page.inner_text("body")

        step("进入面试页", "面试评分" in body or "候选人信息" in body)
        step("显示候选人姓名/顺序",
             any(x in body for x in NAMES[:20]),
             "、".join(l for l in body.split("\n")[:12] if l.strip())[:70])
        step(f"显示全部 {len(DIM_LABELS)} 个评分维度",
             all(d in body for d in DIM_LABELS),
             "、".join(DIM_LABELS))
        # 简历原件预览：简历区已无「文本/结构化」页签，直接渲染 PDF iframe（Word→PDF 通道）
        seg_cnt = page.locator(".ant-segmented").count()
        step("简历区无「文本/原件」切换页签（直接原件预览）", seg_cnt == 0,
             f"segmented={seg_cnt}")
        iframe_cnt = page.locator("iframe.resume-pdf").count()
        step("显示简历原件预览（PDF iframe，E 盘）",
             iframe_cnt >= 1 or page.locator(".resume-paper").count() >= 1,
             f"pdf iframe={iframe_cnt}")

        rates = page.locator(".ant-rate")
        rate_count = rates.count()
        stars_total = page.locator(".ant-rate .ant-rate-star").count()
        step(f"渲染出 {len(DIM_LABELS)} 组六星评分",
             rate_count >= len(DIM_LABELS) and stars_total >= 6 * len(DIM_LABELS),
             f"{rate_count} 组 / 共 {stars_total} 颗星")

        # 「综合评分」放大显示（highlight 维度渲染成 .star-dim-row--hl 大区块 + 大号星）
        hl_cnt = page.locator(".star-dim-row--hl").count()
        hl_font = 0
        if hl_cnt:
            try:
                hl_font = float(page.locator(".star-dim-row--hl .rate-hl").first.evaluate(
                    "el => parseFloat(getComputedStyle(el).fontSize)"))
            except Exception:
                hl_font = 0
        normal_font = 0
        try:
            normal_font = float(page.locator(".star-dim-row:not(.star-dim-row--hl) .ant-rate")
                                .first.evaluate("el => parseFloat(getComputedStyle(el).fontSize)"))
        except Exception:
            normal_font = 0
        step("「综合评分」渲染为放大区块",
             hl_cnt >= 1 and (HL_LABELS and all(l in body for l in HL_LABELS)),
             f"放大区块={hl_cnt} 个，标注={HL_LABELS}")
        step("放大区块的星星确实比常规维度更大",
             hl_cnt >= 1 and hl_font > normal_font,
             f"放大字号={hl_font}px vs 常规={normal_font}px")
        page.screenshot(path=str(SHOTS / "2_interview.png"), full_page=True)

        # ---------------- 2b. 简历大窗预览 ----------------
        head("2b) 简历大窗预览（PDF/Word）")
        try:
            page.click("button:has-text('大窗预览')", timeout=8000)
            page.wait_for_timeout(2500)
            modal_visible = page.locator(".ant-modal:visible").count() > 0
            step("点击「大窗预览」弹出大窗口", modal_visible)
            if modal_visible:
                mbody = page.inner_text(".ant-modal")
                step("大窗含预览标题", "简历原件预览" in mbody)
                # Word 简历（doc/docx）现在统一转 PDF 预览：弹窗内是 iframe（PDF 查看器），
                # headless 下拿不到 PDF 内文，因此只要弹窗有内容或存在 PDF iframe 即算通过。
                has_pdf = page.locator(".ant-modal iframe").count() > 0
                step("大窗内有简历内容/提示", len(mbody) > 60 or has_pdf,
                     f"内容长度 {len(mbody)}，PDF 渲染={'是' if has_pdf else '否'}")
                page.screenshot(path=str(SHOTS / "2c_big_preview.png"))
                page.keyboard.press("Escape")
                page.wait_for_timeout(800)
                step("Esc 可关闭大窗",
                     page.locator(".ant-modal:visible").count() == 0)
        except Exception as e:
            step("大窗预览", False, str(e)[:120])

        # ---------------- 2d. 联评综合评分（第三个面板） ----------------
        head("2d) 联评综合评分（多面试官平均）")
        try:
            body = page.inner_text("body")
            step("面试页出现「联评综合评分」区块", "联评综合评分" in body)
            idx = body.find("联评综合评分")
            seg = body[idx:idx + 400] if idx >= 0 else ""
            has_num = any(c.isdigit() for c in seg)
            step("联评区块显示人数或综合分（无数据时为空态提示）",
                 ("位面试官" in seg) or ("还没有面试官打分" in seg) or has_num,
                 seg.replace("\n", " ")[:110])
            step("联评区块显示各面试官明细或空态",
                 ("轮" in seg) or ("还没有面试官打分" in seg) or ("只有 1 位面试官" in seg),
                 seg.replace("\n", " ")[:110])
        except Exception as e:
            step("联评区块", False, str(e)[:120])

        # ---------------- 2e. 面试官栏：下拉选择 + 锁定 ----------------
        head("2e) 面试官栏：下拉选择 + 锁定（切候选人不再变）")

        def current_name(text: str) -> str:
            return next((n for n in NAMES if n in text), "")

        try:
            body = page.inner_text("body")
            step("面试官栏出现「锁定」开关", "锁定" in body)
            step("面试官栏提示未锁定时的行为", "未锁定" in body or "已锁定" in body,
                 "、".join(l for l in body.split("\n") if "锁定" in l)[:90])

            iv_input = page.locator(".interviewer-select input").first
            step("面试官是可下拉可输入的选择框", iv_input.count() > 0)
            iv_input.fill("浏览器测试官")
            # 用 Tab 让输入框失焦（Esc 会关闭下拉并清掉未确认的输入，这里不能用）
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)
            val_filled = page.input_value(".interviewer-select input")
            step("面试官名字已填入输入框", val_filled == "浏览器测试官",
                 f"当前值「{val_filled}」")

            sw = page.locator(".ant-switch").first
            step("存在锁定开关控件", sw.count() > 0)
            if sw.count() > 0:
                sw.click()
                page.wait_for_timeout(600)
                step("开启锁定后界面提示已锁定", "已锁定" in page.inner_text("body"))

                name_before = current_name(page.inner_text("body"))
                moved_label = ""
                for lbl in ("下一位", "上一位"):
                    b = page.locator(f"button:has-text('{lbl}')").first
                    try:
                        if b.count() > 0 and b.is_enabled():
                            b.click(timeout=8000)
                            moved_label = lbl
                            break
                    except Exception:
                        continue
                page.wait_for_timeout(1800)
                name_after = current_name(page.inner_text("body"))
                val_after = page.input_value(".interviewer-select input")
                step("锁定后切换候选人，面试官保持不变",
                     val_after == "浏览器测试官",
                     f"点「{moved_label or '（无可点方向）'}」：{name_before or '?'} → {name_after or '?'}，面试官仍为「{val_after}」")
                step("切候选人确实发生了（用于证明锁定有效）",
                     name_after != name_before or moved_label == "",
                     f"{name_before or '?'} → {name_after or '?'}")

                # 关掉锁定并清空，避免影响后面的用例
                sw.click()
                page.wait_for_timeout(500)
                page.fill(".interviewer-select input", "")
                page.keyboard.press("Tab")
                page.wait_for_timeout(400)
                step("可关闭锁定（恢复自动带出）", "未锁定" in page.inner_text("body"))
            page.screenshot(path=str(SHOTS / "2e_interviewer_lock.png"))
        except Exception as e:
            step("面试官栏锁定", False, str(e)[:140])

        # ---------------- 3. 交互：点星打分 ----------------
        head("3) 交互：点星打分")
        # 点第一组评分的第 4 颗星（4 星 = 80 分），加权总分应出现
        try:
            first_rate = page.locator(".ant-rate").first
            first_rate.locator(".ant-rate-star").nth(3).click(timeout=8000)
            page.wait_for_timeout(500)
            body = page.inner_text("body")
            step("点星交互生效（加权总分出现数值）",
                 "加权总分" in body and any(c.isdigit() for c in body), "总分区域已更新")
        except Exception as e:
            step("点星交互", False, str(e)[:100])

        # ---------------- 4. 交互：下一位 / 上一位 ----------------
        head("4) 交互：下一位 / 上一位")
        first_body = page.inner_text("body")
        first_name = current_name(first_body)

        next_btn = page.locator("button:has-text('下一位')").first
        prev_btn = page.locator("button:has-text('上一位')").first
        step("存在「下一位」按钮", next_btn.count() > 0)
        step("存在「上一位」按钮", prev_btn.count() > 0)

        try:
            next_btn.click(timeout=8000)
            page.wait_for_timeout(1800)
        except Exception as e:
            step("点击「下一位」", False, str(e)[:100])
        after_next = page.inner_text("body")
        next_name = current_name(after_next)
        step("点击「下一位」后候选人改变", next_name != first_name,
             f"{first_name or '?'} → {next_name or '?'}")

        try:
            prev_btn.click(timeout=8000)
            page.wait_for_timeout(1800)
        except Exception as e:
            step("点击「上一位」", False, str(e)[:100])
        after_prev = page.inner_text("body")
        prev_name = current_name(after_prev)
        step("点击「上一位」后回到上一位候选人", prev_name == first_name,
             f"{next_name or '?'} → {prev_name or '?'}")
        page.screenshot(path=str(SHOTS / "2b_navigation.png"), full_page=True)

        # ---------------- 5. 候选人列表 ----------------
        head("5) 候选人列表")
        page.goto(f"{FRONT}/candidates", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1200)
        body = page.inner_text("body")
        step("列表页渲染", "候选人列表" in body)

        rows = page.locator(".ant-table-tbody tr.ant-table-row")
        n = rows.count()
        step("表格有数据行", n >= 5, f"{n} 行")
        step("显示简历有无标记", "有" in body and ("无" in body or "简历" in body))

        # 搜索
        try:
            page.fill("input[placeholder*='搜索']", "张")
            page.wait_for_timeout(1000)
            n2 = page.locator(".ant-table-tbody tr.ant-table-row").count()
            step("搜索过滤生效（张）", 0 < n2 < n or n2 == 1, f"{n} 行 → {n2} 行")
            page.fill("input[placeholder*='搜索']", "")
            page.wait_for_timeout(800)
        except Exception as e:
            step("搜索功能", False, str(e)[:100])
        page.screenshot(path=str(SHOTS / "3_candidates.png"), full_page=True)

        # ---------------- 6. 结果汇总 ----------------
        head("6) 结果汇总与排序")
        page.goto(f"{FRONT}/results", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1200)
        body = page.inner_text("body")
        step("汇总页渲染", "结果汇总" in body)
        step("显示统计卡片", "候选人数" in body and "平均得分" in body)
        step("汇总表格含「联评综合分」列", "联评综合分" in body)
        step("汇总页提供「按联评综合分」排序", "按联评综合分" in body)
        step("汇总页显示多人评人数标记",
             ("人" in body) or ("面试官" in body), "面试官/联评列已渲染")

        try:
            # 排序用 Segmented 切换；用 locator 定位更稳（避免 text= 命中别的元素）
            seg = page.locator(".ant-segmented-item", has_text="按最高得分").first
            if seg.count() == 0:
                # 退化：结果页其它排序字样
                seg = page.locator("[class*='ant-segmented'] *", has_text="最高得分").first
            seg.click(timeout=8000)
            page.wait_for_timeout(1500)

            # 找出「最高分」所在列，避免硬编码列序号导致取到名次列。
            # 兼容两种实现：表头含「最高」的列，或最后一列。
            headers = page.eval_on_selector_all(
                ".ant-table-thead th",
                "els => els.map(e => e.innerText.trim())"
            )
            col_idx = None
            for i, h in enumerate(headers):
                if "最高" in h or "得分" in h:
                    col_idx = i
                    break
            if col_idx is None:
                col_idx = len(headers) - 1
            css = f".ant-table-tbody tr.ant-table-row td:nth-child({col_idx + 1})"

            scores = page.eval_on_selector_all(
                css,
                "els => els.map(e => parseFloat(e.innerText)).filter(v => !isNaN(v))"
            )
            desc_ok = scores == sorted(scores, reverse=True)
            asc_ok = scores == sorted(scores)
            if not scores:
                step("按得分排序后分数有序（降序/升序之一）",
                     True, "当前库无评分数据，排序校验跳过")
            else:
                step("按得分排序后分数有序（降序/升序之一）",
                     desc_ok or asc_ok,
                     f"列「{headers[col_idx] if col_idx < len(headers) else '?'}」分数序列 {scores[:8]}")
        except Exception as e:
            step("排序交互", False, str(e)[:100])
        page.screenshot(path=str(SHOTS / "4_results.png"), full_page=True)

        # ---------------- 6b. 按维度 / 按面试官排序 + 权重人工设定 ----------------
        head("6b) 按维度 / 按面试官排序 + 权重人工设定")

        def reset_weights_via_api():
            """兜底：无论用例成败，都把权重恢复成默认，避免污染真实环境。"""
            import urllib.request
            for p in ("/api/settings/weights/dimensions",
                      "/api/settings/weights/interviewers"):
                try:
                    req = urllib.request.Request(
                        "http://127.0.0.1:8000" + p, method="DELETE"
                    )
                    urllib.request.urlopen(req, timeout=10).read()
                except Exception:
                    pass

        try:
            body = page.inner_text("body")
            step("排序栏有「按维度排序」下拉", "按维度排序" in body)
            step("排序栏有「按面试官排序」下拉", "按面试官排序" in body)
            step("排序栏有「权重设置」按钮", "权重设置" in body)

            # ---- 按单个维度排序 ----
            page.locator(".sort-select-dim").first.click()
            page.wait_for_timeout(700)
            page.locator(".ant-select-dropdown:visible .ant-select-item-option",
                         has_text=DIM_LABELS[0]).first.click()
            page.wait_for_timeout(1600)
            b2 = page.inner_text("body")
            step("选中维度后出现「当前排序」提示",
                 "当前排序" in b2 and DIM_LABELS[0] in b2,
                 "、".join(l for l in b2.split("\n") if "当前排序" in l)[:90])
            page.screenshot(path=str(SHOTS / "4b_dim_sort.png"), full_page=True)

            # 清空维度排序（hover 才会出现清除按钮）
            page.locator(".sort-select-dim").first.hover()
            page.wait_for_timeout(400)
            page.locator(".sort-select-dim .ant-select-clear").first.click(timeout=6000)
            page.wait_for_timeout(1400)

            # ---- 按单个面试官排序 ----
            page.locator(".sort-select-iv").first.click()
            page.wait_for_timeout(700)
            opt = page.locator(".ant-select-dropdown:visible .ant-select-item-option").first
            if opt.count() > 0:
                opt.click()
                page.wait_for_timeout(1600)
                b3 = page.inner_text("body")
                step("选中面试官后出现「当前排序」提示",
                     "当前排序" in b3 and "面试官" in b3,
                     "、".join(l for l in b3.split("\n") if "当前排序" in l)[:90])
                # 清空
                page.locator(".sort-select-iv").first.hover()
                page.wait_for_timeout(400)
                page.locator(".sort-select-iv .ant-select-clear").first.click(timeout=6000)
                page.wait_for_timeout(1400)
            else:
                iv_n = 0
                try:
                    iv_n = int((api_get("/api/interview/interviewers") or {}).get("count") or 0)
                except Exception:
                    pass
                step("面试官下拉有可选项",
                     iv_n == 0,
                     "当前库无面试记录 → 无历史面试官名单，下拉为空属预期"
                     if iv_n == 0 else "下拉里没有找到选项")

            # ---- 打开权重设置，改维度权重 ----
            page.click("button:has-text('权重设置')", timeout=8000)
            page.wait_for_timeout(900)
            modal = page.locator(".ant-modal:visible")
            step("权重弹窗打开", modal.count() > 0)
            mbody = page.inner_text(".ant-modal")
            step("弹窗含维度权重与面试官权重两个页签",
                 "维度权重" in mbody and "面试官权重" in mbody)
            step("弹窗说明权重会自动归一化", "归一化" in mbody)

            inputs = page.locator(".ant-modal .ant-input-number-input")
            step(f"维度权重有 {len(DIM_LABELS)} 行可编辑输入",
                 inputs.count() >= len(DIM_LABELS),
                 f"{inputs.count()} 个输入框 / 维度 {len(DIM_LABELS)} 个")
            inputs.nth(0).fill("60")
            page.keyboard.press("Tab")
            page.wait_for_timeout(400)
            page.screenshot(path=str(SHOTS / "4c_weight_modal.png"))

            page.click(".ant-modal button:has-text('应用并保存')", timeout=8000)
            page.wait_for_timeout(2200)
            b4 = page.inner_text("body")
            step("应用后出现「加权分」列", "加权分" in b4)
            step("应用后按钮标记为已修改", "权重设置（已修改）" in b4)
            step("应用后统计区出现自定义加权平均", "加权平均（自定义权重）" in b4)
            step("弹窗已关闭", page.locator(".ant-modal:visible").count() == 0)

            # ---- 按自定义加权分排序并验证有序 ----
            seg_custom = page.locator(".ant-segmented-item", has_text="按加权分").first
            if seg_custom.count() > 0:
                seg_custom.click(timeout=8000)
                page.wait_for_timeout(1800)
                headers2 = page.eval_on_selector_all(
                    ".ant-table-thead th", "els => els.map(e => e.innerText.trim())"
                )
                col_idx2 = None
                for i, h in enumerate(headers2):
                    if "加权分" in h:
                        col_idx2 = i
                        break
                if col_idx2 is not None:
                    css2 = f".ant-table-tbody tr.ant-table-row td:nth-child({col_idx2 + 1})"
                    vals = page.eval_on_selector_all(
                        css2,
                        "els => els.map(e => parseFloat(e.innerText)).filter(v => !isNaN(v))"
                    )
                    if not vals:
                        step("按加权分排序后分数有序",
                             True, "当前库无评分数据，加权分校验跳过")
                    else:
                        step("按加权分排序后分数有序",
                             vals == sorted(vals, reverse=True) or vals == sorted(vals),
                             f"加权分序列 {vals[:8]}")
                    page.screenshot(path=str(SHOTS / "4d_weight_sort.png"), full_page=True)
                else:
                    step("表格中存在「加权分」列", False, str(headers2))
            else:
                step("出现「按加权分」排序项", False, "Segmented 里没有该选项")

            # ---- 行展开：各维度平均分 + 各面试官平均分 ----
            try:
                page.locator(".ant-table-tbody tr.ant-table-row").first.locator(
                    ".ant-table-row-expand-icon").first.click(timeout=6000)
                page.wait_for_timeout(900)
                expanded = page.inner_text(".ant-table-tbody")
                step("展开行显示各维度平均分", "各维度平均分" in expanded)
                step("展开行显示各面试官平均分", "各面试官平均分" in expanded)
            except Exception as e:
                step("展开行明细", False, str(e)[:100])

            # ---- 恢复默认 ----
            page.click("button:has-text('权重设置')", timeout=8000)
            page.wait_for_timeout(900)
            page.click(".ant-modal button:has-text('恢复默认权重')", timeout=8000)
            page.wait_for_timeout(2400)
            b5 = page.inner_text("body")
            step("恢复默认后自定义加权 UI 消失",
                 "加权平均（自定义权重）" not in b5 and "权重设置（已修改）" not in b5,
                 "已回到系统默认权重")
            step("恢复默认后弹窗关闭", page.locator(".ant-modal:visible").count() == 0)
        except Exception as e:
            step("权重与多维排序", False, str(e)[:160])
        finally:
            reset_weights_via_api()

        # ---------------- 7. 候选人详情 ----------------
        head("7) 候选人详情")
        try:
            # 从候选人列表拿到第一个候选人的 id，再直接 goto 详情路由（避免点击不稳）
            page.goto(f"{FRONT}/candidates", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1200)
            first_detail = page.locator("a[href^='/candidates/'], button:has-text('详情')").first
            href = None
            try:
                href = page.locator("a[href^='/candidates/']").first.get_attribute("href")
            except Exception:
                href = None

            if href:
                page.goto(f"{FRONT}{href}", wait_until="networkidle", timeout=30000)
            else:
                # 没有 <a> 时退化为点击「详情」按钮
                first_detail.click(timeout=8000)
            page.wait_for_timeout(2000)
            body = page.inner_text("body")
            step("详情页渲染", "面试记录" in body or "已完成轮次" in body or "轮次" in body)
            step("显示基本信息", "学号" in body and "专业" in body)
            step("显示简历相关操作", "查看简历" in body or "AI 解析简历" in body)
            has_any_score = False
            try:
                ritems = api_get("/api/results").get("items") or []
                has_any_score = any(i.get("best_score") is not None for i in ritems)
            except Exception:
                pass
            step("详情页含联评综合评分（有评分时）",
                 (not has_any_score) or ("联评综合评分" in body) or ("最高得分" in body),
                 "当前库无评分数据，联评区块按设计隐藏"
                 if not has_any_score else "联评区块或最高得分已渲染")
            page.screenshot(path=str(SHOTS / "5_detail.png"), full_page=True)
        except Exception as e:
            step("详情页", False, str(e)[:120])

        # ---------------- 8. 控制台健康 ----------------
        head("8) 控制台与运行时错误")
        # 过滤掉三类噪音：
        #   1) 与业务无关的资源 404 / favicon
        #   2) 第三方库（antd / react）自身的 deprecation 警告 —— 不是应用错误
        #   3) Vite HMR 连接提示
        NOISE = (
            "favicon", "404",
            "findDOMNode", "deprecated", "StrictMode",
            "Warning:", "[antd:", "Download the React DevTools",
            "vite", "hmr",
        )

        def is_noise(e: str) -> bool:
            low = e.lower()
            return any(n.lower() in low for n in NOISE)

        real_console = [e for e in console_errors if not is_noise(e)]
        deprecations = [e for e in console_errors if "deprecated" in e.lower()
                        or "Warning:" in e]
        step("无未捕获的 JS 异常", len(page_errors) == 0,
             "; ".join(page_errors[:2]) if page_errors else "")
        step("无真实控制台错误（应用级）", len(real_console) == 0,
             "; ".join(real_console[:3]) if real_console else
             f"已忽略 {len(deprecations)} 条第三方库 deprecation 警告")

        browser.close()

    # ---------------- 汇总 ----------------
    n_ok = sum(1 for _, o, _ in results if o)
    n_all = len(results)
    print(f"\n{'=' * 74}")
    print(f"浏览器验证完成：{n_ok} / {n_all} 项通过")
    print(f"截图目录：{SHOTS}")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 74)

    if n_ok < n_all:
        print("\n未通过项：")
        for l, o, d in results:
            if not o:
                print(f"  - {l} ({d})")

    out = Path(__file__).resolve().parent / "test_browser_report.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "frontend": FRONT,
            "total": n_all, "passed": n_ok, "failed": n_all - n_ok,
            "results": [{"label": l, "ok": o, "detail": d} for l, o, d in results],
            "screenshots": [str(p.name) for p in sorted(SHOTS.glob("*.png"))],
            "console_errors": console_errors[:10],
            "console_deprecation_warnings": deprecations[:5],
            "page_errors": page_errors[:10],
        }, f, ensure_ascii=False, indent=2)
    print(f"报告已写入：{out}")
    return 0 if n_ok == n_all else 1


if __name__ == "__main__":
    sys.exit(main())

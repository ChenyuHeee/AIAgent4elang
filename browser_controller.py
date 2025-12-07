import asyncio
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

from playwright.async_api import BrowserContext, Page, async_playwright


@dataclass
class PlaywrightConfig:
    browser: str
    headless: bool
    user_data_dir: str
    default_timeout_ms: int
    start_url: str
    context: Dict[str, Any]


class BrowserController:
    def __init__(self, cfg: PlaywrightConfig) -> None:
        self.cfg = cfg
        self._browser: Optional[BrowserContext] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> Page:
        pw = await async_playwright().start()
        launch_fn = getattr(pw, self.cfg.browser)
        pathlib.Path(self.cfg.user_data_dir).mkdir(parents=True, exist_ok=True)
        self._browser = await launch_fn.launch_persistent_context(
            user_data_dir=self.cfg.user_data_dir,
            headless=self.cfg.headless,
            **self.cfg.context,
        )
        self._context = self._browser
        self._context.set_default_timeout(self.cfg.default_timeout_ms)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        if self.cfg.start_url:
            await self._page.goto(self.cfg.start_url)
        return self._page

    async def expand_collapsed_content(self) -> None:
        # Try common expand/show-original triggers to reveal hidden question text.
        candidates = [
            "text=查看原文",
            "text=展开",
            "text=展开全文",
            "text=显示全文",
            "text=原文",
            "text=more",
            "text=show more",
        ]
        for sel in candidates:
            loc = self.page.locator(sel)
            if await loc.count() > 0:
                try:
                    await loc.first.click(timeout=2000)
                    await self.page.wait_for_timeout(300)
                except Exception:  # noqa: BLE001
                    continue

    async def stop(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started")
        return self._page

    async def read_question_block(self) -> Dict[str, Any]:
        page = self.page
        await page.wait_for_timeout(300)  # give DOM a moment to settle
        await self.expand_collapsed_content()
        await self._auto_scroll(page)

        async def first_non_empty(selectors: list[str]) -> str:
            for sel in selectors:
                texts = [t.strip() for t in await page.locator(sel).all_inner_texts()]
                texts = [t for t in texts if t]
                if texts:
                    return texts[0]
            return ""

        async def longest_line(selectors: list[str]) -> str:
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    if await loc.count() == 0:
                        continue
                    text = await loc.first.text_content(timeout=2000)
                    if text:
                        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                        if lines:
                            return max(lines, key=len)
                except Exception:
                    continue
            return ""

        async def collect_options(selectors: list[str]) -> list[str]:
            seen = set()
            results: list[str] = []
            for sel in selectors:
                texts = [t.strip() for t in await page.locator(sel).all_inner_texts()]
                for t in texts:
                    if t and t not in seen:
                        seen.add(t)
                        results.append(t)
            return results

        async def collect_form_options_via_js() -> list[str]:
            script = r"""
            (() => {
              const nodes = Array.from(document.querySelectorAll('label, button, [role="option"], li, [data-option], [data-testid="option"], [data-qa="option"], input[type="radio"], input[type="checkbox"]'));
              const texts = [];
              for (const n of nodes) {
                let t = '';
                if (n.tagName === 'INPUT') {
                  if (n.labels && n.labels.length) {
                    t = Array.from(n.labels).map(l => l.innerText || '').join(' ').trim();
                  } else if (n.getAttribute('aria-label')) {
                    t = n.getAttribute('aria-label') || '';
                  }
                } else {
                  t = n.innerText || '';
                  if (!t && n.getAttribute('aria-label')) {
                    t = n.getAttribute('aria-label') || '';
                  }
                }
                t = t.replace(/\s+/g, ' ').trim();
                if (t && t.length <= 200) texts.push(t);
              }
              return Array.from(new Set(texts));
            })();
            """
            try:
                options: list[str] = await page.evaluate(script)
                return options
            except Exception:
                return []

        question_selectors = [
            "[data-question]",
            "[data-testid='question']",
            "[data-qa='question']",
            "main h1",
            "main h2",
            "article h1",
            "article h2",
            "article p",
            "section h1",
            "section h2",
            ".question",
            ".question-stem",
            ".stem",
            ".title",
            "div[role='heading']",
            "div[role='article']",
        ]
        option_selectors = [
            "[data-option]",
            "[data-testid='option']",
            "[data-qa='option']",
            "label",
            "li",
            "button",
            "[role='option']",
            "input[type='radio']+label",
            "input[type='checkbox']+label",
            ".answer",
            ".answer-title",
            ".answer-desc",
        ]

        def merge_lists(a: list[str], b: list[str]) -> list[str]:
            seen = set(a)
            out = list(a)
            for x in b:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        async def extract_from_frame(frame) -> Dict[str, Any]:
            # Collect all Praxis-style question blocks on the page, keeping their order.
            praxis_items = await frame.evaluate(
                r"""
                (() => {
                  const toText = (el) => (el ? (el.innerText || '').replace(/\s+/g, ' ').trim() : '');
                  const blocks = Array.from(document.querySelectorAll('.praxis-item'));
                  const items = blocks.map((b, idx) => {
                    const question = toText(b.querySelector('.praxis-desc') || b.querySelector('.wrap-text'));
                    const options = [];
                    const answers = b.querySelectorAll('.praxis-info .answer');
                    answers.forEach(a => {
                      const title = toText(a.querySelector('.answer-title'));
                      const desc = toText(a.querySelector('.answer-desc'));
                      const combined = (title ? title + (desc ? '. ' + desc : '') : desc).trim();
                      if (combined) options.push(combined);
                    });
                    const preview = toText(b);
                    return { idx, question, options, preview };
                  });
                  if (!items.length) return null;
                  return items;
                })();
                """
            )

            praxis_focus = None
            if praxis_items:
                # Pick the first Praxis block as the default focus; we'll still return all items.
                praxis_focus = praxis_items[0]

            async def f_first_non_empty(selectors: list[str]) -> str:
                for sel in selectors:
                    texts = [t.strip() for t in await frame.locator(sel).all_inner_texts()]
                    texts = [t for t in texts if t]
                    if texts:
                        return texts[0]
                return ""

            async def f_longest_line(selectors: list[str]) -> str:
                for sel in selectors:
                    try:
                        loc = frame.locator(sel)
                        if await loc.count() == 0:
                            continue
                        text = await loc.first.text_content(timeout=1500)
                        if text:
                            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                            if lines:
                                return max(lines, key=len)
                    except Exception:
                        continue
                return ""

            q_text = praxis_focus.get("question", "") if praxis_focus else ""
            opts = merge_lists([], [str(o).strip() for o in praxis_focus.get("options", [])]) if praxis_focus else []
            preview = praxis_focus.get("preview", "") if praxis_focus else ""

            if not q_text:
                q_text = await f_first_non_empty(question_selectors)
            if not q_text:
                q_text = await f_longest_line(["main", "article", "section", "body"])
            if not opts:
                opts = await collect_options(option_selectors)
            if not opts:
                opts = await collect_form_options_via_js()
            # Praxis page specialized extraction (class-based) fallback if still empty
            if not opts:
                try:
                    praxis = await frame.evaluate(
                        r"""
                        (() => {
                            const toText = (el) => (el ? (el.innerText || '').replace(/\s+/g,' ').trim() : '');
                            const block = document.querySelector('.praxis-item');
                            const info = document.querySelector('.praxis-info');
                            let question = '';
                            if (block) {
                                const desc = block.querySelector('.praxis-desc') || block.querySelector('.wrap-text');
                                question = toText(desc);
                            }
                            const options = [];
                            if (info) {
                                const answers = Array.from(info.querySelectorAll('.answer'));
                                for (const a of answers) {
                                    const title = toText(a.querySelector('.answer-title'));
                                    const desc = toText(a.querySelector('.answer-desc'));
                                    const combined = (title ? title + (desc ? '. ' + desc : '') : desc).trim();
                                    if (combined) options.push(combined);
                                }
                            }
                            return { question, options };
                        })();
                        """
                    )
                    if praxis:
                        if praxis.get("question") and not q_text:
                            q_text = str(praxis.get("question", "")).strip()
                        if praxis.get("options"):
                            opts = merge_lists(opts, [str(o).strip() for o in praxis["options"] if str(o).strip()])
                except Exception:
                    pass
            # Accessibility fallback for options
            try:
                ax = await frame.accessibility.snapshot()
                if ax:
                    names: list[str] = []
                    stack = [ax]
                    while stack:
                        node = stack.pop()
                        role = node.get("role") if isinstance(node, dict) else None
                        name = node.get("name") if isinstance(node, dict) else None
                        if role in {"option", "radio", "checkbox", "listitem", "button"} and name:
                            names.append(name)
                        children = node.get("children") if isinstance(node, dict) else None
                        if children:
                            stack.extend(children)
                    if names:
                        opts = merge_lists(opts, [n.strip() for n in names if n.strip()])
            except Exception:
                pass

            if not preview:
                body_text = await frame.text_content("body") or ""
                preview = " ".join(body_text.split())[:800]
            return {"question": q_text, "options": opts, "preview": preview, "items": praxis_items or []}

        main_res = await extract_from_frame(page)
        question_text = main_res.get("question", "")
        options = main_res.get("options", [])
        preview = main_res.get("preview", "")
        all_items = main_res.get("items", []) or []

        # If no options or question empty, try iframes.
        if len(page.frames) > 1:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    fr_res = await extract_from_frame(frame)
                    if fr_res.get("items"):
                        all_items.extend(fr_res["items"])
                    if not question_text and fr_res.get("question"):
                        question_text = fr_res["question"]
                    options = merge_lists(options, fr_res.get("options", []))
                    if not preview and fr_res.get("preview"):
                        preview = fr_res["preview"]
                except Exception:
                    continue

        # If we collected multiple items, use the first one to populate question/options for backward compatibility.
        if all_items and not question_text:
            question_text = all_items[0].get("question", "")
        if all_items and not options:
            options = all_items[0].get("options", [])

        return {"question": question_text, "options": options, "debug_body_preview": preview, "items": all_items}

    async def _auto_scroll(self, page: Page) -> None:
        # Scroll through the page to trigger lazy rendering / virtualization.
        try:
            await page.evaluate(
                """
                async () => {
                  const delay = ms => new Promise(r => setTimeout(r, ms));
                  const total = document.body.scrollHeight;
                  const step = Math.max(300, Math.floor(total / 6));
                  for (let y = 0; y <= total; y += step) {
                    window.scrollTo(0, y);
                    await delay(120);
                  }
                  window.scrollTo(0, 0);
                }
                """
            )
        except Exception:
            pass

    async def dismiss_popups(self) -> None:
        # Hide common overlays/popups that may block clicks or appear after accidental taps.
        try:
            await self.page.evaluate(
                """
                (() => {
                  const hide = (sel) => document.querySelectorAll(sel).forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    el.style.pointerEvents = 'none';
                  });
                  hide('.van-overlay, .van-popup, .van-dialog, .van-toast, .word-pop, .word-popup, .popover, [class*="popup"], [role="dialog"]');
                  const closeBtns = document.querySelectorAll('.van-action-sheet__close, .van-popup__close-icon, .van-dialog__confirm, .van-dialog__cancel, .popup-close');
                  closeBtns.forEach(btn => { try { btn.click(); } catch (e) {} });
                })();
                """
            )
        except Exception:
            pass

    async def click_option(self, locator: str) -> None:
        await self.dismiss_popups()

        loc = self.page.locator(locator).first

        # Best-effort wait before clicking.
        try:
            await loc.wait_for(state="visible", timeout=3000)
        except Exception:
            pass

        try:
            await loc.click(timeout=6000)
            return
        except Exception:
            pass

        try:
            handle = await loc.element_handle()
            if handle:
                await handle.scroll_into_view_if_needed()
                await handle.click(timeout=6000, force=True)
                return
        except Exception:
            pass

        # Final attempt with force on locator.
        await loc.click(timeout=6000, force=True)

    async def click_praxis_option(self, item_index: int, option_text: str) -> bool:
        """Click option inside a specific .praxis-item by index (0-based). Returns True if clicked."""
        await self.dismiss_popups()

        def norm(s: str) -> str:
            return " ".join((s or "").replace("\u00a0", " ").split()).strip().lower()

        target_text = norm(option_text)

        locator_item = self.page.locator(".praxis-item").nth(item_index)
        answers = locator_item.locator(".praxis-info .answer")
        count = await answers.count()
        for i in range(count):
            ans = answers.nth(i)
            title = norm(await ans.locator(".answer-title").text_content() or "")
            desc = norm(await ans.locator(".answer-desc").text_content() or "")
            combined = (title + (" " + desc if desc else "")).strip()

            def match_candidate(candidate: str) -> bool:
                if not candidate:
                    return False
                return candidate == target_text or candidate in target_text or target_text in candidate

            if match_candidate(combined) or match_candidate(desc) or match_candidate(title):
                try:
                    await ans.scroll_into_view_if_needed()
                except Exception:
                    pass
                try:
                    await ans.click(timeout=6000)
                    return True
                except Exception:
                    pass
                try:
                    await ans.click(timeout=6000, force=True)
                    return True
                except Exception:
                    pass
        return False

    async def safe_stop(self) -> None:
        try:
            await self.stop()
        except Exception:
            pass

    async def fill_answer(self, locator: str, text: str) -> None:
        await self.page.locator(locator).fill(text)

    async def screenshot(self, path: str) -> None:
        await self.page.screenshot(path=path, full_page=True)


def load_config(config: Dict[str, Any]) -> PlaywrightConfig:
    cfg = config["playwright"]
    return PlaywrightConfig(
        browser=cfg.get("browser", "chromium"),
        headless=bool(cfg.get("headless", False)),
        user_data_dir=cfg.get("user_data_dir", "./user_data"),
        default_timeout_ms=int(cfg.get("default_timeout_ms", 15000)),
        start_url=cfg.get("start_url", ""),
        context=cfg.get("context", {}),
    )

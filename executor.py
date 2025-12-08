import asyncio
import json
import pathlib
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv

from browser_controller import BrowserController, PlaywrightConfig, load_config as load_pw_config
from nlp_agent import DeepSeekClient, answer_question, load_config as load_ds_config
from selector_finder import build_text_locators, select_best
from utils.logger import log_struct, setup_logger
from vision_ocr import OCRConfig, VisionOCR, load_config as load_ocr_config


def read_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs(paths: Dict[str, str]) -> None:
    for target in paths.values():
        pathlib.Path(target).mkdir(parents=True, exist_ok=True)


async def handle_single_question(
    browser: BrowserController,
    nlp: DeepSeekClient,
    ocr: VisionOCR,
    logger,
    config: Dict[str, Any],
) -> None:
    # Ensure browser is running; if user closed the window, signal caller to exit.
    try:
        page = browser.page
    except RuntimeError:
        page = await browser.start()
    if page.is_closed():
        raise RuntimeError("浏览器已关闭")
    await browser.dismiss_popups()
    input("请手动在浏览器中打开题目页面，准备好后按回车继续…")

    await browser.dismiss_popups()
    try:
        dom = await browser.read_question_block()
    except Exception as exc:  # noqa: BLE001
        if "Target closed" in str(exc) or "浏览器" in str(exc):
            raise RuntimeError("浏览器已关闭") from exc
        raise
    question = dom.get("question", "").strip()
    options: List[str] = dom.get("options", [])
    preview = dom.get("debug_body_preview", "")
    items = dom.get("items", []) or []
    log_struct(
        logger,
        "dom_parsed",
        question_len=len(question),
        options=len(options),
        preview=preview[:200],
        items=len(items),
    )

    # Always dump the latest page HTML for debugging multi-question/fill pages.
    try:
        dump_path = pathlib.Path(config["paths"].get("logs", "./data/logs")) / "page_dump_debug.html"
        html = await browser.page.content()
        dump_path.write_text(html, encoding="utf-8")
        log_struct(logger, "page_dump_saved", path=str(dump_path))
    except Exception:
        pass

    if not options and not items:
        dump_path = pathlib.Path(config["paths"].get("logs", "./data/logs")) / "page_dump.html"
        html = await browser.page.content()
        dump_path.write_text(html, encoding="utf-8")
        screenshot_path = pathlib.Path(config["paths"].get("screenshots", "./data/screenshots")) / "no_options.png"
        await browser.screenshot(str(screenshot_path))
        log_struct(
            logger,
            "options_missing",
            dump=str(dump_path),
            screenshot=str(screenshot_path),
            hint="未识别到选项，将尝试以填空题处理；请检查 page_dump.html 以优化选择器",
        )

    if not question and preview:
        question = preview[:300]
        log_struct(logger, "question_preview_fallback", text_len=len(question))

    if not question and config.get("agent", {}).get("enable_ocr_fallback", False):
        screenshot_path = pathlib.Path(config["paths"]["screenshots"]) / "ocr_fallback.png"
        await browser.screenshot(str(screenshot_path))
        ocr_result = await ocr.run(str(screenshot_path))
        question = ocr_result.get("text", "")
        log_struct(logger, "ocr_used", text_len=len(question))

    if not question:
        dump_path = pathlib.Path(config["paths"]["logs"]) / "page_dump.txt"
        dump_path.write_text(preview, encoding="utf-8")
        log_struct(logger, "question_missing", hint="未识别到题干，请调整 read_question_block 的选择器", dump=str(dump_path))
        return

    # If there are multiple praxis items, iterate through each; otherwise handle the single question.
    tasks = items if items else [{"question": question, "options": options, "preview": preview}]
    collected_answers: List[str] = []

    batch_results: Dict[int, Any] = {}
    if len(tasks) > 1:
        try:
            payload = []
            for i, t in enumerate(tasks):
                opts = t.get("options", []) or []
                qtext = (t.get("question") or "").strip()
                if not qtext:
                    qtext = (t.get("preview") or preview or "")[:300]
                qtype = "single" if opts else "fill"
                payload.append({"idx": i + 1, "question": qtext, "options": opts, "type": qtype})
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a careful exam assistant. Use only provided options when they exist; never invent new options. "
                        "Return ONLY a JSON array: [{\"idx\": number, \"answer\": array or string}]. "
                        "For choice questions, answer is an array of the original option text (keep any letter prefixes). "
                        "For fill-in questions (no options), answer is a concise string. Keep items ordered by idx. No extra words."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            raw = await nlp.chat(messages)
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "idx" in item and "answer" in item:
                        batch_results[int(item["idx"])] = item
            if len(batch_results) < len(tasks):
                debug_path = pathlib.Path(config["paths"].get("logs", "./data/logs")) / "llm_batch_debug.json"
                debug_path.write_text(json.dumps({"payload": payload, "raw": raw}, ensure_ascii=False, indent=2), encoding="utf-8")
                log_struct(logger, "model_answer_batch_partial", count=len(batch_results), expected=len(tasks), dump=str(debug_path))
            else:
                log_struct(logger, "model_answer_batch", count=len(batch_results))
        except Exception as exc:  # noqa: BLE001
            log_struct(logger, "model_answer_batch_failed", error=str(exc))

    for idx, item in enumerate(tasks, start=1):
        q = (item.get("question") or "").strip()
        opts_list: List[str] = item.get("options", []) or []
        log_struct(logger, "dom_item", idx=idx, question_len=len(q), options=len(opts_list))

        if not opts_list:
            log_struct(
                logger,
                "options_missing_item",
                idx=idx,
                hint="未识别到选项，按填空题处理；请检查页面结构或选择器",
            )

        if not q and item.get("preview"):
            q = str(item.get("preview", ""))[:300]
            log_struct(logger, "question_preview_fallback", idx=idx, text_len=len(q))

        if not q and preview:
            q = str(preview)[:300]
            log_struct(logger, "question_page_preview_fallback", idx=idx, text_len=len(q))

        if not q and config.get("agent", {}).get("enable_ocr_fallback", False):
            screenshot_path = pathlib.Path(config["paths"]["screenshots"]) / f"ocr_fallback_{idx}.png"
            await browser.screenshot(str(screenshot_path))
            ocr_result = await ocr.run(str(screenshot_path))
            q = ocr_result.get("text", "")
            log_struct(logger, "ocr_used", idx=idx, text_len=len(q))

        if not q:
            dump_path = pathlib.Path(config["paths"]["logs"]) / f"page_dump_{idx}.txt"
            dump_path.write_text(preview, encoding="utf-8")
            log_struct(logger, "question_missing", idx=idx, hint="未识别到题干，请调整 read_question_block 的选择器", dump=str(dump_path))
            continue

        q_type = "single" if opts_list else "fill"
        answer: Dict[str, Any]
        if batch_results.get(idx):
            answer = {"type": q_type, "answer": batch_results[idx].get("answer")}
            log_struct(logger, "model_answer", idx=idx, raw=answer, source="batch")
        else:
            answer = await answer_question(nlp, q, opts_list, q_type)
            log_struct(logger, "model_answer", idx=idx, raw=answer, source="single")

        # Echo question and options for visibility.
        print(f"【题干】第{idx}题：{q}")
        if opts_list:
            opts_text = " | ".join(opts_list)
            print(f"【选项】{opts_text}")

        ans_val = answer.get("answer")
        def to_label_only(val: Any) -> str:
            # If answer like 'A.xxx' or 'A ' keep leading token for summary; else keep raw.
            s = str(val)
            parts = s.split(None, 1)
            if parts and len(parts[0]) <= 3 and parts[0].rstrip('.').isalpha():
                return parts[0].rstrip('.')
            # Also handle formats like 'A.' or 'A、B'
            return s

        if isinstance(ans_val, list):
            ans_text = "、".join([str(a) for a in ans_val])
            summary_label = "、".join([to_label_only(a) for a in ans_val])
        else:
            ans_text = str(ans_val)
            summary_label = to_label_only(ans_val)
        print(f"【答案】第{idx}题：{ans_text}")

        if isinstance(answer.get("answer"), list) and opts_list:
            first_option = str(answer["answer"][0])

            clicked = False
            if items:
                # Prefer item-scoped click to avoid cross-question collisions.
                try:
                    clicked = await browser.click_praxis_option(idx - 1, first_option)
                except Exception as exc:  # noqa: BLE001
                    log_struct(logger, "click_failed", idx=idx, mode="praxis", error=str(exc))
                if clicked:
                    log_struct(logger, "clicked", idx=idx, mode="praxis", option=first_option)

            if not clicked:
                locators = build_text_locators(first_option)
                candidate = select_best(locators)
                if candidate:
                    try:
                        await browser.click_option(candidate.locator)
                        log_struct(logger, "clicked", idx=idx, locator=candidate.locator)
                    except Exception as exc:  # noqa: BLE001
                        log_struct(logger, "click_failed", idx=idx, locator=candidate.locator, error=str(exc))

        collected_answers.append(f"第{idx}题：{summary_label}")

    await browser.screenshot(str(pathlib.Path(config["paths"]["screenshots"]) / "after.png"))
    if collected_answers:
        print("【本页答案汇总】" + "； ".join(collected_answers))


async def main() -> None:
    load_dotenv()
    config = read_config("config.yaml")
    ensure_dirs(config.get("paths", {}))

    logger = setup_logger("agent", config["paths"].get("logs", "./data/logs"))
    pw_config: PlaywrightConfig = load_pw_config(config)
    ds_config = load_ds_config(config)
    ocr_config: OCRConfig = load_ocr_config(config)

    browser = BrowserController(pw_config)
    ocr = VisionOCR(ocr_config)
    nlp = DeepSeekClient(ds_config)

    try:
        # Start once; allow multiple Q&A rounds until the user closes the browser.
        await browser.start()
        while True:
            try:
                await handle_single_question(browser, nlp, ocr, logger, config)
            except RuntimeError as exc:
                if "浏览器已关闭" in str(exc):
                    break
                raise
            except KeyboardInterrupt:
                break
            try:
                prompt = "按回车开始下一题（直接关闭浏览器窗口则结束）…"
                input(prompt)
            except EOFError:
                break
            except KeyboardInterrupt:
                break

            # If the user closed the browser window, stop the loop.
            try:
                if browser.page.is_closed():
                    break
            except Exception:
                break
    finally:
        try:
            await browser.stop()
        except Exception:
            pass
        try:
            await nlp.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())

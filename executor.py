import asyncio
import pathlib
from typing import Any, Dict, List

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

    if not options:
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
            hint="选项未识别：请查看 page_dump.html，可能在 iframe/shadow 里，或需要新的选择器",
        )
        return

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

    for idx, item in enumerate(tasks, start=1):
        q = (item.get("question") or "").strip()
        opts_list: List[str] = item.get("options", []) or []
        log_struct(logger, "dom_item", idx=idx, question_len=len(q), options=len(opts_list))

        if not opts_list:
            if not items:  # single-question flow keeps previous handling
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
                    hint="选项未识别：请查看 page_dump.html，可能在 iframe/shadow 里，或需要新的选择器",
                )
            continue

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

        answer = await answer_question(nlp, q, opts_list, "single")
        log_struct(logger, "model_answer", idx=idx, raw=answer)

        ans_val = answer.get("answer")
        if isinstance(ans_val, list):
            ans_text = "、".join([str(a) for a in ans_val])
        else:
            ans_text = str(ans_val)
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

        collected_answers.append(f"第{idx}题：{ans_text}")

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

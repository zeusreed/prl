# core/translator.py

import os
import time
import re
import shutil
import google.generativeai as genai
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from docx import Document
# <-- ИЗМЕНЕНИЕ: Мы будем использовать этот импорт для надежной обработки ошибок
from google.api_core.exceptions import ResourceExhausted

from .project_manager import PROJECTS_DIR, ProjectManager


# Обычная, последовательная функция перевода
def translation_process(project_data, progress_queue, stop_event):
    pm = ProjectManager()
    try:
        project_name = project_data["project_name"]
        completed_chapters_list = project_data["completed_chapters_list"]

        temp_dir = os.path.join(PROJECTS_DIR, project_name, "temp")
        if not project_data["resume"]:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            completed_chapters_list = []
        os.makedirs(temp_dir, exist_ok=True)

        genai.configure(api_key=project_data["api_key"])
        model = genai.GenerativeModel(project_data["model"])

        glossary = {}
        for line in project_data["glossary"].split('\n'):
            if '->' in line and not line.strip().startswith('#'):
                parts = line.split('->', 1)
                original, translation = parts[0].strip(), parts[1].strip()
                if original and translation:
                    glossary[original] = translation

        progress_queue.put(("log", f"Используется модель: {project_data['model']}"))
        book = epub.read_epub(project_data["epub_path"])
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        total_items = len(items)

        for i, item in enumerate(items):
            if stop_event.is_set():
                break

            if i in completed_chapters_list:
                progress_queue.put(("log", f"Глава {i + 1} уже переведена. Пропускаем."))
                progress_queue.put(("progress", (i + 1, total_items)))
                continue

            progress_queue.put(("progress", (i, total_items)))
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            original_text = soup.get_text(separator='\n', strip=True)
            if not original_text.strip():
                progress_queue.put(("log", f"Глава {i + 1} пустая, пропускаем."))
                completed_chapters_list.append(i)
                pm.update_completed_chapters(project_name, completed_chapters_list)
                progress_queue.put(("progress", (i + 1, total_items)))
                continue

            if project_data["use_regex"]:
                for original, translation in glossary.items():
                    try:
                        original_text = re.sub(original, translation, original_text)
                    except re.error as e:
                        progress_queue.put(("log", f"Ошибка RegEx: '{original}' -> {e}"))
            else:
                for original, translation in glossary.items():
                    original_text = original_text.replace(original, translation)

            if not original_text.strip():
                progress_queue.put(("log", f"Глава {i + 1} стала пустой после глоссария. Пропускаем."))
                continue

            prompt = project_data["prompt"].format(text_to_translate=original_text)

            # --- НАЧАЛО ИЗМЕНЕНИЙ: Улучшенный механизм повторных попыток ---
            translated_text = ""
            max_retries = 5
            retry_delay = 10

            for attempt in range(max_retries):
                if stop_event.is_set():
                    break
                try:
                    progress_queue.put(
                        ("log", f"Глава {i + 1}: Отправка запроса в API (попытка {attempt + 1}/{max_retries})..."))
                    response = model.generate_content(prompt)
                    translated_text = response.text if response.text else ""
                    progress_queue.put(("log", f"Глава {i + 1}: Ответ от API получен."))
                    break  # Если запрос успешен, выходим из цикла попыток

                # <-- ИЗМЕНЕНИЕ: Ловим КОНКРЕТНУЮ ошибку исчерпания квоты
                except ResourceExhausted as e:
                    progress_queue.put((
                        "log",
                        f"⚠️ Превышен лимит API для главы {i + 1}. Попытка {attempt + 1}/{max_retries}. "
                        f"Ждем {retry_delay} секунд..."
                    ))
                    # Ждем перед следующей попыткой, проверяя сигнал остановки каждую секунду
                    for _ in range(retry_delay):
                        if stop_event.is_set(): break
                        time.sleep(1)
                    if stop_event.is_set(): break
                    retry_delay *= 2  # Удваиваем задержку (10s, 20s, 40s...)

                # <-- ИЗМЕНЕНИЕ: Ловим все остальные ошибки API, которые не являются ошибкой квоты
                except Exception as e:
                    # Если это любая другая ошибка (неверный ключ, проблема с моделью и т.д.),
                    # нет смысла пытаться снова. Пробрасываем ее наверх, чтобы остановить процесс.
                    progress_queue.put(("log", f"Критическая ошибка API: {e}"))
                    raise e
            # --- КОНЕЦ ИЗМЕНЕНИЙ ---

            if stop_event.is_set():
                break

            if not translated_text:
                progress_queue.put(("log",
                                    f"❌ Не удалось получить перевод для главы {i + 1} после {max_retries} попыток. Пропускаем."))
                continue

            temp_file_path = os.path.join(temp_dir, f"chapter_{i:04d}.txt")
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                chapter_title_tag = soup.find(['h1', 'h2', 'h3'])
                chapter_title = chapter_title_tag.get_text(strip=True) if chapter_title_tag else f"Глава {i + 1}"
                f.write(f"<h1>{chapter_title}</h1>\n{translated_text}")

            completed_chapters_list.append(i)
            pm.update_completed_chapters(project_name, completed_chapters_list)

            progress_queue.put(("progress", (i + 1, total_items)))
            if not stop_event.is_set() and project_data["delay"] > 0:
                progress_queue.put(("log", f"Задержка на {project_data['delay']} сек..."))
                time.sleep(project_data["delay"])

        if not stop_event.is_set():
            progress_queue.put(("log", "Все главы переведены. Собираем DOCX..."))
            doc = Document()
            metadata_title = book.get_metadata('DC', 'title')
            doc.add_heading(metadata_title[0][0] if metadata_title else "Переведенная книга", 0)

            if os.path.exists(temp_dir) and os.listdir(temp_dir):
                for filename in sorted(os.listdir(temp_dir)):
                    if filename.endswith(".txt"):
                        with open(os.path.join(temp_dir, filename), 'r', encoding='utf-8') as f:
                            content = f.read().split('\n', 1)
                            title = content[0].replace("<h1>", "").replace("</h1>", "")
                            text = content[1] if len(content) > 1 else ""
                            doc.add_heading(title, level=1)
                            doc.add_paragraph(text)
                            doc.add_page_break()

            doc.save(project_data["output_path"])
            pm.cleanup_project(project_name)
            progress_queue.put(("done", None))
        else:
            progress_queue.put(("log", "Перевод отменен. Прогресс сохранен."))

    except Exception as e:
        import traceback
        progress_queue.put(("error", traceback.format_exc()))
    finally:
        # Этот сигнал всегда должен отправляться, чтобы GUI разблокировался
        progress_queue.put(("finish_signal", None))
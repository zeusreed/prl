# gui/app.py

import os
import sys
import time
import threading
import queue
import pyperclip
import customtkinter as ctk
from tkinter import filedialog, messagebox, TclError

from core.project_manager import ProjectManager
from core.translator import translation_process
# Используем УЖЕ ИСПРАВЛЕННЫЙ ApiKeyManager
from core.api_key_manager import ApiKeyManager

FALLBACK_MODELS = ["gemini-1.5-flash-latest", "gemini-1.5-pro-latest", "gemini-1.0-pro"]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.pm = ProjectManager()
        self.key_manager = ApiKeyManager()

        self.title("Менеджер Переводов v8.6 (Log Export)")
        self.geometry("1100x800")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.is_running = False
        self.translation_thread = None
        self.stop_event = threading.Event()
        self.progress_queue = queue.Queue()

        self.is_modifier_pressed = False

        self.api_key_name_var = ctk.StringVar()
        self.epub_path_var = ctk.StringVar()
        self.output_path_var = ctk.StringVar()
        self.project_name_var = ctk.StringVar(value="<Выберите проект>")
        self.model_var = ctk.StringVar(value=FALLBACK_MODELS[0])
        self.delay_var = ctk.StringVar(value="2.0")
        self.regex_var = ctk.BooleanVar(value=False)
        self.batch_mode_var = ctk.StringVar(value="Файл")

        self.build_ui()
        self.update_project_list()
        self.update_api_key_list()
        self.check_queue()

    def add_default_bindings(self, widget):
        def on_modifier_press(event):
            self.is_modifier_pressed = True

        def on_modifier_release(event):
            self.is_modifier_pressed = False

        if sys.platform == "darwin":
            self.bind_all("<KeyPress-Command>", on_modifier_press, add='+')
            self.bind_all("<KeyRelease-Command>", on_modifier_release, add='+')
        else:
            self.bind_all("<KeyPress-Control_L>", on_modifier_press, add='+')
            self.bind_all("<KeyPress-Control_R>", on_modifier_press, add='+')
            self.bind_all("<KeyRelease-Control_L>", on_modifier_release, add='+')
            self.bind_all("<KeyRelease-Control_R>", on_modifier_release, add='+')

        def on_key_press(event):
            if self.is_modifier_pressed:
                key = event.keysym.lower()
                if key == 'v':
                    try:
                        clipboard_text = pyperclip.paste()
                        if isinstance(clipboard_text, str):
                            try:
                                widget.delete("sel.first", "sel.last")
                            except TclError:
                                pass
                            widget.insert(ctk.INSERT, clipboard_text)
                    except Exception:
                        pass
                    return "break"
                elif key == 'c':
                    try:
                        selected_text = widget.get("sel.first", "sel.last")
                        pyperclip.copy(selected_text)
                    except TclError:
                        pass
                    return "break"
                elif key == 'x':
                    try:
                        selected_text = widget.get("sel.first", "sel.last")
                        pyperclip.copy(selected_text)
                        widget.delete("sel.first", "sel.last")
                    except TclError:
                        pass
                    return "break"
                elif key == 'a':
                    if isinstance(widget, ctk.CTkEntry):
                        widget.select_range(0, 'end')
                    elif isinstance(widget, ctk.CTkTextbox):
                        widget.tag_add("sel", "1.0", "end")
                    return "break"

        widget.bind("<KeyPress>", on_key_press)

    def build_ui(self):
        unicode_font = ("Segoe UI", 14)
        bold_font = ("Segoe UI", 16, "bold")

        left_panel = ctk.CTkFrame(self, width=250)
        left_panel.grid(row=0, column=0, rowspan=5, padx=10, pady=10, sticky="ns")
        ctk.CTkLabel(left_panel, text="Проекты", font=bold_font).pack(pady=10)
        self.project_menu = ctk.CTkOptionMenu(left_panel, variable=self.project_name_var, command=self.load_project)
        self.project_menu.pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(left_panel, text="Новый проект", command=self.create_new_project).pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(left_panel, text="Сохранить проект", command=self.save_project).pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(left_panel, text="Удалить проект", fg_color="red", hover_color="#C41E3A",
                      command=self.delete_project).pack(pady=5, padx=10, fill="x")
        separator1 = ctk.CTkFrame(left_panel, height=2, fg_color="gray50")
        separator1.pack(pady=10, fill="x", padx=5)
        ctk.CTkLabel(left_panel, text="Настройки проекта", font=bold_font).pack(pady=10)
        model_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        model_frame.pack(pady=5, padx=10, fill="x")
        model_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(model_frame, text="Модель Gemini:").grid(row=0, column=0, columnspan=2, padx=0, pady=(5, 0),
                                                              sticky="w")
        self.model_menu = ctk.CTkOptionMenu(model_frame, variable=self.model_var, values=FALLBACK_MODELS)
        self.model_menu.grid(row=1, column=0, sticky="ew")
        self.update_models_button = ctk.CTkButton(model_frame, text="Обновить", width=80,
                                                  command=self.start_model_list_update)
        self.update_models_button.grid(row=1, column=1, padx=(5, 0))
        ctk.CTkLabel(left_panel, text="Задержка между главами (сек):").pack(padx=10, pady=(10, 0), anchor="w")
        self.delay_entry = ctk.CTkEntry(left_panel, textvariable=self.delay_var)
        self.delay_entry.pack(pady=5, padx=10, fill="x")
        self.add_default_bindings(self.delay_entry)
        self.regex_checkbox = ctk.CTkCheckBox(left_panel, text="Включить RegEx в глоссарии", variable=self.regex_var)
        self.regex_checkbox.pack(pady=10, padx=10, fill="x")
        separator2 = ctk.CTkFrame(left_panel, height=2, fg_color="gray50")
        separator2.pack(pady=10, fill="x", padx=5)
        ctk.CTkLabel(left_panel, text="Управление", font=bold_font).pack(pady=10)
        self.start_button = ctk.CTkButton(left_panel, text="🚀 Начать перевод", command=self.start_translation)
        self.start_button.pack(pady=5, padx=10, fill="x")
        self.stop_button = ctk.CTkButton(left_panel, text="❌ Отмена", fg_color="red", hover_color="#C41E3A",
                                         command=self.stop_translation, state="disabled")
        self.stop_button.pack(pady=5, padx=10, fill="x")
        separator3 = ctk.CTkFrame(left_panel, height=2, fg_color="gray50")
        separator3.pack(pady=10, fill="x", padx=5)
        self.theme_switch = ctk.CTkSwitch(left_panel, text="Тёмная тема", command=self.toggle_theme)
        self.theme_switch.pack(pady=10, padx=10)
        if ctk.get_appearance_mode() == "Dark": self.theme_switch.select()

        settings_frame = ctk.CTkFrame(self)
        settings_frame.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(settings_frame, text="API Ключ:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        key_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        key_frame.grid(row=0, column=1, sticky="ew")
        key_frame.grid_columnconfigure(0, weight=1)
        self.api_key_menu = ctk.CTkOptionMenu(key_frame, variable=self.api_key_name_var)
        self.api_key_menu.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="ew")
        self.manage_keys_button = ctk.CTkButton(key_frame, text="...", width=40, command=self.open_key_manager_window)
        self.manage_keys_button.grid(row=0, column=1, pady=5)
        source_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        source_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10)
        source_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(source_frame, text="Режим:").grid(row=0, column=0, padx=(0, 5))
        self.mode_switch = ctk.CTkSegmentedButton(source_frame, values=["Файл", "Папка"], variable=self.batch_mode_var)
        self.mode_switch.grid(row=0, column=1, pady=5, sticky="w")
        ctk.CTkLabel(source_frame, text="Источник:").grid(row=1, column=0)
        self.epub_path_entry = ctk.CTkEntry(source_frame, textvariable=self.epub_path_var,
                                            placeholder_text="Путь к файлу или папке")
        self.epub_path_entry.grid(row=1, column=1, sticky="ew")
        self.add_default_bindings(self.epub_path_entry)
        self.select_source_button = ctk.CTkButton(source_frame, text="...", width=40, command=self.select_source)
        self.select_source_button.grid(row=1, column=2, padx=5)
        ctk.CTkLabel(source_frame, text="Папка/Файл\nрезультата:").grid(row=2, column=0)
        self.output_path_entry = ctk.CTkEntry(source_frame, textvariable=self.output_path_var,
                                              placeholder_text="Путь для сохранения")
        self.output_path_entry.grid(row=2, column=1, sticky="ew")
        self.add_default_bindings(self.output_path_entry)
        self.select_output_button = ctk.CTkButton(source_frame, text="...", width=40, command=self.select_output)
        self.select_output_button.grid(row=2, column=2, padx=5)
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        self.tab_view.add("Промпт")
        self.tab_view.add("Глоссарий")
        self.grid_rowconfigure(1, weight=1)
        self.prompt_textbox = ctk.CTkTextbox(self.tab_view.tab("Промпт"), font=unicode_font)
        self.prompt_textbox.pack(expand=True, fill="both", padx=5, pady=5)
        self.add_default_bindings(self.prompt_textbox)
        self.glossary_textbox = ctk.CTkTextbox(self.tab_view.tab("Глоссарий"), font=unicode_font)
        self.glossary_textbox.pack(expand=True, fill="both", padx=5, pady=5)
        self.glossary_textbox.insert("0.0", "# Формат: Оригинал -> Перевод\n# Пример:\n(?i)naruto -> Наруто")
        self.add_default_bindings(self.glossary_textbox)

        progress_frame = ctk.CTkFrame(self)
        progress_frame.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(pady=5, padx=10, fill="x")
        self.progress_label = ctk.CTkLabel(progress_frame, text="Ожидание запуска...")
        self.progress_label.pack(pady=5, padx=10)
        self.progress_bar.set(0)

        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.log_textbox = ctk.CTkTextbox(log_frame, state="disabled", font=unicode_font)
        self.log_textbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 0))
        self.add_default_bindings(self.log_textbox)
        self.save_log_button = ctk.CTkButton(log_frame, text="Сохранить лог в файл", command=self.save_log)
        self.save_log_button.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

    def select_source(self):
        if self.batch_mode_var.get() == "Файл":
            path = filedialog.askopenfilename(title="Выберите EPUB файл", filetypes=[("EPUB files", "*.epub")])
            if path: self.epub_path_var.set(path)
        else:
            path = filedialog.askdirectory(title="Выберите папку с EPUB файлами")
            if path: self.epub_path_var.set(path)

    def select_output(self):
        if self.batch_mode_var.get() == "Файл":
            path = filedialog.asksaveasfilename(title="Сохранить как...", filetypes=[("Word Document", "*.docx")],
                                                defaultextension=".docx")
            if path: self.output_path_var.set(path)
        else:
            path = filedialog.askdirectory(title="Выберите папку для сохранения результатов")
            if path: self.output_path_var.set(path)

    def save_log(self):
        self.log_textbox.configure(state="normal")
        log_content = self.log_textbox.get("1.0", "end-1c")
        if not self.is_running:
            pass
        else:
            self.log_textbox.configure(state="disabled")

        if not log_content.strip():
            messagebox.showinfo("Информация", "Лог пуст, нечего сохранять.", parent=self)
            return

        filepath = filedialog.asksaveasfilename(
            title="Сохранить лог как...",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                self.log(f"Лог успешно сохранен в: {filepath}")
            except Exception as e:
                self.log(f"Ошибка сохранения лога: {e}")
                messagebox.showerror("Ошибка", f"Не удалось сохранить лог:\n{e}", parent=self)

    # ---> ВОТ КЛЮЧЕВАЯ ФУНКЦИЯ С ИЗМЕНЕНИЯМИ <---
    def open_key_manager_window(self):
        if hasattr(self, 'key_window') and self.key_window.winfo_exists():
            self.key_window.focus()
            return

        self.key_window = ctk.CTkToplevel(self)
        self.key_window.title("Менеджер API ключей")
        self.key_window.geometry("500x350")
        self.key_window.transient(self)  # Окно будет поверх главного

        # Фрейм со списком ключей
        scrollable_frame = ctk.CTkScrollableFrame(self.key_window, label_text="Сохраненные ключи")
        scrollable_frame.pack(pady=10, padx=10, fill="both", expand=True)
        selected_key_name = ctk.StringVar()  # Не используется, но может пригодиться

        def refresh_key_list():
            # Очищаем старый список
            for widget in scrollable_frame.winfo_children():
                widget.destroy()
            # Заполняем новым списком
            for name in self.key_manager.get_key_names():
                key_frame = ctk.CTkFrame(scrollable_frame)
                key_frame.pack(fill="x", pady=2)
                # Просто метка с именем ключа
                ctk.CTkLabel(key_frame, text=name).pack(side="left", padx=5)

                # Функция для замыкания, чтобы передать правильное имя
                def delete_closure(key_name=name):
                    if messagebox.askyesno("Подтверждение", f"Удалить ключ '{key_name}'?", parent=self.key_window):
                        success, message = self.key_manager.delete_key(key_name)
                        if success:
                            self.update_api_key_list()
                            refresh_key_list()
                        else:
                            # Показываем ошибку, если не удалось удалить (например, нет прав на запись)
                            messagebox.showerror("Ошибка", message, parent=self.key_window)

                ctk.CTkButton(key_frame, text="Удалить", width=60, fg_color="red", command=delete_closure).pack(
                    side="right", padx=5)

        refresh_key_list()

        # ---> ДОБАВЛЕНЫ ПОЛЯ ВВОДА И КНОПКА СОХРАНЕНИЯ <---
        # Фрейм для добавления нового ключа
        entry_frame = ctk.CTkFrame(self.key_window)
        entry_frame.pack(pady=10, padx=10, fill="x")

        ctk.CTkLabel(entry_frame, text="Имя:").grid(row=0, column=0, padx=5, pady=5)
        name_entry = ctk.CTkEntry(entry_frame, placeholder_text="Название для ключа (например, 'Мой ключ 1')")
        name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.add_default_bindings(name_entry)

        ctk.CTkLabel(entry_frame, text="Ключ:").grid(row=1, column=0, padx=5, pady=5)
        value_entry = ctk.CTkEntry(entry_frame, placeholder_text="Вставьте сам API-ключ сюда")
        value_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.add_default_bindings(value_entry)

        entry_frame.grid_columnconfigure(1, weight=1)

        # Функция, которая будет вызываться при нажатии кнопки
        def save_key():
            name, value = name_entry.get(), value_entry.get()
            # Вызываем исправленный метод, который возвращает результат
            success, message = self.key_manager.add_or_update_key(name, value)

            # Показываем пользователю результат операции
            if success:
                # Если все хорошо, обновляем списки и очищаем поля
                refresh_key_list()
                self.update_api_key_list()
                # Выбираем только что добавленный ключ в главном окне
                self.api_key_menu.set(name.strip())
                name_entry.delete(0, "end")
                value_entry.delete(0, "end")
                messagebox.showinfo("Успех", message, parent=self.key_window)
            else:
                # Если произошла ошибка, показываем ее
                messagebox.showerror("Ошибка", message, parent=self.key_window)

        # САМА КНОПКА СОХРАНЕНИЯ
        ctk.CTkButton(self.key_window, text="Сохранить / Обновить ключ", command=save_key).pack(pady=10, padx=10,
                                                                                                fill="x")

    def update_api_key_list(self):
        key_names = self.key_manager.get_key_names()
        if not key_names:
            key_names = ["<Нет ключей>"]
        current_selection = self.api_key_name_var.get()
        self.api_key_menu.configure(values=key_names)
        if current_selection in key_names:
            self.api_key_menu.set(current_selection)
        else:
            self.api_key_menu.set(key_names[0])

    def get_api_key(self):
        selected_name = self.api_key_name_var.get()
        if selected_name and selected_name != "<Нет ключей>":
            return self.key_manager.get_key_value(selected_name)
        key_from_env = os.environ.get("GOOGLE_API_KEY")
        if key_from_env:
            return key_from_env
        return None

    def save_project(self):
        project_name = self.project_name_var.get()
        if not project_name or project_name == "<Выберите проект>":
            messagebox.showerror("Ошибка", "Не выбрано имя проекта для сохранения.")
            return
        try:
            data = self.pm.load(project_name)
            completed_chapters = data.get("completed_chapters", [])
        except (FileNotFoundError, Exception):
            completed_chapters = []
        project_data = {
            "api_key_name": self.api_key_name_var.get(),
            "epub_path": self.epub_path_var.get(),
            "output_path": self.output_path_var.get(),
            "prompt": self.prompt_textbox.get("1.0", "end-1c"),
            "glossary": self.glossary_textbox.get("1.0", "end-1c"),
            "model": self.model_var.get(),
            "delay": float(self.delay_var.get() or 2.0),
            "use_regex": self.regex_var.get(),
            "completed_chapters": completed_chapters
        }
        self.pm.save(project_name, project_data)
        self.log(f"Проект '{project_name}' успешно сохранен.")
        if project_name not in self.project_menu.cget("values"):
            self.update_project_list()

    def load_project(self, project_name):
        if project_name == "<Выберите проект>" or project_name == "<Нет проектов>":
            self.clear_fields()
            return
        self.clear_fields()
        self.project_name_var.set(project_name)
        try:
            data = self.pm.load(project_name)
            key_name = data.get("api_key_name", "")
            if key_name in self.key_manager.get_key_names():
                self.api_key_name_var.set(key_name)
            self.epub_path_var.set(data.get("epub_path", ""))
            self.output_path_var.set(data.get("output_path", ""))
            self.prompt_textbox.insert("1.0", data.get("prompt", ""))
            self.glossary_textbox.insert("1.0", data.get("glossary", ""))
            self.model_var.set(data.get("model", FALLBACK_MODELS[0]))
            self.delay_var.set(str(data.get("delay", 2.0)))
            self.regex_var.set(data.get("use_regex", False))
            self.log(f"Проект '{project_name}' загружен.")
        except Exception as e:
            self.log(f"Ошибка при загрузке проекта: {e}")

    def start_translation(self):
        if self.is_running:
            return

        source_path = self.epub_path_var.get()
        output_path = self.output_path_var.get()
        if not source_path or not output_path:
            messagebox.showerror("Ошибка", "Пути источника и результата не могут быть пустыми.")
            return

        files_to_process = []
        if self.batch_mode_var.get() == "Файл":
            if not source_path.lower().endswith(".epub"):
                messagebox.showerror("Ошибка", "В режиме 'Файл' источник должен быть .epub файлом.")
                return
            files_to_process.append({"input": source_path, "output": output_path})
        else:
            if not os.path.isdir(source_path):
                messagebox.showerror("Ошибка", "В режиме 'Папка' источник должен быть папкой.")
                return
            if not os.path.isdir(output_path):
                os.makedirs(output_path, exist_ok=True)
            for filename in os.listdir(source_path):
                if filename.lower().endswith(".epub"):
                    base, _ = os.path.splitext(filename)
                    files_to_process.append({
                        "input": os.path.join(source_path, filename),
                        "output": os.path.join(output_path, f"{base}_translated.docx")
                    })

        if not files_to_process:
            messagebox.showerror("Ошибка", "Не найдено EPUB файлов для обработки.")
            return

        self.is_running = True
        self.stop_event.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.project_menu.configure(state="disabled")

        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

        self.translation_thread = threading.Thread(target=self.batch_translation_manager, args=(files_to_process,))
        self.translation_thread.start()

    def batch_translation_manager(self, files_to_process):
        total_books = len(files_to_process)
        self.progress_queue.put(("log", f"Начинаем пакетную обработку. Всего книг: {total_books}"))

        for i, file_info in enumerate(files_to_process):
            if self.stop_event.is_set():
                self.progress_queue.put(("log", "Пакетная обработка отменена пользователем."))
                break

            self.progress_queue.put(
                ("log", f"--- Книга {i + 1}/{total_books}: {os.path.basename(file_info['input'])} ---"))
            project_data = self.collect_project_data()
            if not project_data:
                break

            project_data["epub_path"] = file_info["input"]
            project_data["output_path"] = file_info["output"]
            translation_process(project_data, self.progress_queue, self.stop_event)

        if not self.stop_event.is_set():
            self.progress_queue.put(("log", "🎉 Вся пакетная обработка завершена!"))
        self.progress_queue.put(("finish_signal", None))

    def collect_project_data(self):
        api_key = self.get_api_key()
        if not api_key:
            self.progress_queue.put(("error", "API-ключ не найден!"))
            return None
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            self.progress_queue.put(("error", "Неверное значение задержки!"))
            return None

        project_name = self.project_name_var.get()
        if project_name == "<Выберите проект>" or project_name == "<Нет проектов>":
            project_name = f"temp_project_{int(time.time())}"

        resume_translation = False
        completed_chapters = []
        try:
            data = self.pm.load(project_name)
            completed_chapters = data.get("completed_chapters", [])
            if completed_chapters:
                resume_translation = True
        except (FileNotFoundError, Exception):
            pass

        return {
            "api_key": api_key, "prompt": self.prompt_textbox.get("1.0", "end-1c"),
            "glossary": self.glossary_textbox.get("1.0", "end-1c"), "model": self.model_var.get(),
            "delay": delay, "use_regex": self.regex_var.get(), "project_name": project_name,
            "resume": resume_translation, "completed_chapters_list": completed_chapters
        }

    def create_new_project(self):
        dialog = ctk.CTkInputDialog(text="Введите имя нового проекта:", title="Создание проекта")
        project_name = dialog.get_input()
        if project_name:
            if os.path.exists(self.pm.get_project_path(project_name)):
                messagebox.showerror("Ошибка", "Проект с таким именем уже существует!")
                return
            self.project_name_var.set(project_name)
            self.clear_fields()
            self.save_project()
            self.update_project_list()
            self.project_menu.set(project_name)

    def clear_fields(self):
        self.epub_path_var.set("")
        self.output_path_var.set("")
        self.prompt_textbox.delete("1.0", "end")
        self.glossary_textbox.delete("1.0", "end")
        self.glossary_textbox.insert("0.0", "# Формат: Оригинал -> Перевод\n# Пример:\n(?i)naruto -> Наруто")
        self.model_var.set(FALLBACK_MODELS[0])
        self.delay_var.set("2.0")
        self.regex_var.set(False)
        self.update_api_key_list()

    def delete_project(self):
        project_name = self.project_name_var.get()
        if not project_name or project_name in ["<Выберите проект>", "<Нет проектов>"]:
            return
        if messagebox.askyesno("Подтверждение", f"Вы уверены, что хотите удалить проект '{project_name}'?"):
            self.pm.delete(project_name)
            self.log(f"Проект '{project_name}' удален.")
            self.update_project_list()
            self.clear_fields()

    def update_project_list(self):
        projects = self.pm.get_project_list()
        if not projects:
            projects = ["<Нет проектов>"]

        current_project = self.project_name_var.get()
        self.project_menu.configure(values=projects)

        if current_project in projects:
            self.project_menu.set(current_project)
        else:
            self.project_menu.set(projects[0])
            if projects[0] not in ["<Выберите проект>", "<Нет проектов>"]:
                self.load_project(projects[0])
            else:
                self.clear_fields()

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f"[{timestamp}] {message}\n")
        self.log_textbox.configure(state="disabled")
        self.log_textbox.see("end")

    def toggle_theme(self):
        ctk.set_appearance_mode("Dark" if self.theme_switch.get() == 1 else "Light")

    def start_model_list_update(self):
        api_key = self.get_api_key()
        if not api_key:
            messagebox.showerror("Ошибка", "Сначала выберите API-ключ для обновления списка моделей.")
            return
        self.update_models_button.configure(text="...", state="disabled")
        threading.Thread(target=self.fetch_models_thread, args=(api_key,)).start()

    def fetch_models_thread(self, api_key):
        import google.generativeai as genai
        try:
            genai.configure(api_key=api_key)
            models = [m.name.replace("models/", "") for m in genai.list_models() if
                      'generateContent' in m.supported_generation_methods]
            self.progress_queue.put(("update_models", models))
        except Exception as e:
            self.progress_queue.put(("log", f"Ошибка получения списка моделей: {e}"))
            self.progress_queue.put(("update_models", None))

    def update_model_menu(self, models):
        current_model = self.model_var.get()
        if models:
            self.model_menu.configure(values=models)
            if current_model in models:
                self.model_menu.set(current_model)
            else:
                self.model_menu.set(models[0])
            self.log("Список моделей успешно обновлен.")
        else:
            self.log("Не удалось обновить список моделей. Используется стандартный набор.")
        self.update_models_button.configure(text="Обновить", state="normal")

    def check_queue(self):
        try:
            while not self.progress_queue.empty():
                message, data = self.progress_queue.get_nowait()
                if message == "log":
                    self.log(data)
                elif message == "progress":
                    current, total = data
                    percentage = current / total if total > 0 else 0
                    self.progress_bar.set(percentage)
                    self.progress_label.configure(text=f"Переведено глав: {current} / {total} ({percentage:.0%})")
                elif message == "done":
                    self.log("✅ Перевод успешно завершен!")
                elif message == "error":
                    self.log(f"❌ ОШИБКА: {data}")
                    self.log_textbox.configure(state="normal")
                elif message == "finish_signal":
                    self.translation_finished()
                elif message == "update_models":
                    self.update_model_menu(data)
        except queue.Empty:
            pass
        finally:
            self.after(100, self.check_queue)

    def stop_translation(self):
        if self.is_running:
            self.log("⚠️ Получен сигнал отмены...")
            self.stop_event.set()
            self.stop_button.configure(text="Останавливаем...", state="disabled")

    def translation_finished(self):
        self.is_running = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(text="❌ Отмена", state="disabled")
        self.project_menu.configure(state="normal")
        self.log_textbox.configure(state="normal")
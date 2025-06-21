# core/api_key_manager.py
import json
import os

API_KEYS_FILE = "api_keys.json"


class ApiKeyManager:
    def __init__(self):
        self.keys = self._load()

    def _load(self):
        if not os.path.exists(API_KEYS_FILE):
            return {}
        try:
            with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Убедимся, что данные - это словарь
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, IOError):
            # Если файл пуст, поврежден или не читается, возвращаем пустой словарь
            return {}

    def _save(self):
        """
        Пытается сохранить ключи в файл.
        Возвращает кортеж (успех: bool, сообщение: str).
        """
        try:
            with open(API_KEYS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.keys, f, indent=4)
            return True, "Данные успешно сохранены."
        except IOError as e:
            # Отлавливаем ошибки прав доступа, переполнения диска и т.д.
            error_message = f"Ошибка записи в файл {API_KEYS_FILE}:\n{e}"
            print(error_message)  # Также выводим в консоль для отладки
            return False, error_message
        except Exception as e:
            # Отлавливаем другие возможные ошибки
            error_message = f"Непредвиденная ошибка при сохранении ключей:\n{e}"
            print(error_message)
            return False, error_message

    def get_key_names(self):
        return list(self.keys.keys())

    def get_key_value(self, name):
        return self.keys.get(name, "")

    def add_or_update_key(self, name, value):
        """
        Добавляет или обновляет ключ и СОХРАНЯЕТ изменения.
        Возвращает кортеж (успех: bool, сообщение: str).
        """
        if not name or not value:
            return False, "Имя и ключ не могут быть пустыми."

        # Проверяем, что имя ключа - это корректная строка без лишних пробелов
        name = name.strip()
        if not name:
            return False, "Имя ключа не может состоять только из пробелов."

        self.keys[name] = value

        # Теперь _save возвращает результат операции
        success, message = self._save()

        if success:
            return True, f"Ключ '{name}' успешно сохранен."
        else:
            # Если сохранение не удалось, откатываем изменение в памяти
            # (хотя это не критично, т.к. при следующем запуске загрузятся старые данные)
            # del self.keys[name] # Это можно раскомментировать при необходимости
            return False, message  # Возвращаем сообщение об ошибке от _save

    def delete_key(self, name):
        if name in self.keys:
            del self.keys[name]
            success, message = self._save()
            if success:
                return True, f"Ключ '{name}' удален."
            else:
                # Если сохранение не удалось, возвращаем ошибку
                return False, message
        return False, "Ключ не найден."
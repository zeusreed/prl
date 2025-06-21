# core/project_manager.py
import os
import json
import shutil

PROJECTS_DIR = "projects"

class ProjectManager:
    def __init__(self):
        if not os.path.exists(PROJECTS_DIR):
            os.makedirs(PROJECTS_DIR)

    def get_project_list(self):
        return [f.replace('.json', '') for f in os.listdir(PROJECTS_DIR) if f.endswith('.json')]

    def get_project_path(self, project_name):
        return os.path.join(PROJECTS_DIR, f"{project_name}.json")

    def load(self, project_name):
        filepath = self.get_project_path(project_name)
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save(self, project_name, project_data):
        filepath = self.get_project_path(project_name)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=4, ensure_ascii=False)

    def delete(self, project_name):
        filepath = self.get_project_path(project_name)
        if os.path.exists(filepath):
            temp_dir = os.path.join(PROJECTS_DIR, project_name, "temp")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.remove(filepath)

    def update_completed_chapters(self, project_name, completed_list):
        filepath = self.get_project_path(project_name)
        with open(filepath, 'r+', encoding='utf-8') as f:
            data = json.load(f)
            data['completed_chapters'] = completed_list
            f.seek(0)
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.truncate()

    def cleanup_project(self, project_name):
        temp_dir = os.path.join(PROJECTS_DIR, project_name, "temp")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        self.update_completed_chapters(project_name, [])
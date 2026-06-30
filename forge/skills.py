import os
import inspect
import importlib.util
from typing import List, Callable, Tuple
from forge.tools import ToolRegistry

def skill(func: Callable) -> Callable:
    """Decorator to mark a function inside a skill bundle's script as a Tool."""
    func.is_skill = True
    return func


class SkillsManager:
    """Discovers, aggregates prompts, and registers tool scripts from folder-based 
    Skill Bundles inside the skills directory.
    """
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = os.path.abspath(skills_dir)

    def load_skills(self, registry: ToolRegistry) -> Tuple[List[str], str]:
        """Scans folder-based skill bundles, imports functions tagged with @skill, 
        and extracts guidelines from SKILL.md.
        
        Returns:
            Tuple[List[str], str]: A list of loaded tool names, and a combined 
              prompt extensions string.
        """
        loaded_tools = []
        combined_prompts = []
        
        if not os.path.exists(self.skills_dir):
            print(f"[Skills Manager Warning] Directory '{self.skills_dir}' does not exist.")
            return loaded_tools, ""
            
        # Iterate over subdirectories in skills/
        for item in os.listdir(self.skills_dir):
            bundle_path = os.path.join(self.skills_dir, item)
            # Skip hidden folders or private helper directories
            if os.path.isdir(bundle_path) and not item.startswith(".") and not item.startswith("_"):
                print(f"[Skills Manager] Discovered Skill Bundle: '{item}'")
                
                # 1. Load cognitive prompts from SKILL.md
                skill_md_path = os.path.join(bundle_path, "SKILL.md")
                if os.path.exists(skill_md_path):
                    try:
                        with open(skill_md_path, "r", encoding="utf-8") as f:
                            md_content = f.read()
                        combined_prompts.append(f"=== Skill: {item} ===\n{md_content}\n")
                        print(f"[Skills Manager] Loaded prompt guidelines from {item}/SKILL.md")
                    except Exception as e:
                        print(f"[Skills Manager Warning] Failed to read {item}/SKILL.md: {str(e)}")
                        
                # 2. Hot-load python execution tools from scripts/ directory
                scripts_path = os.path.join(bundle_path, "scripts")
                if os.path.isdir(scripts_path):
                    for script_file in os.listdir(scripts_path):
                        if script_file.endswith(".py") and not script_file.startswith("_"):
                            filepath = os.path.join(scripts_path, script_file)
                            module_name = f"{item}_{script_file[:-3]}" # Namespace isolation
                            
                            try:
                                spec = importlib.util.spec_from_file_location(module_name, filepath)
                                if spec is None or spec.loader is None:
                                    continue
                                    
                                module = importlib.util.module_from_spec(spec)
                                spec.loader.exec_module(module)
                                
                                # Inspect functions tagged with @skill
                                for name, attr in inspect.getmembers(module):
                                    if inspect.isfunction(attr):
                                        if getattr(attr, "is_skill", False):
                                            registry.register(attr)
                                            loaded_tools.append(name)
                                            print(f"[Skills Manager] Loaded custom tool '{name}' from {item}/scripts/{script_file}")
                                            
                            except Exception as e:
                                print(f"[Skills Manager Warning] Failed to import script '{script_file}' in bundle '{item}': {str(e)}")
                                
        prompt_extension = "\n".join(combined_prompts)
        return loaded_tools, prompt_extension

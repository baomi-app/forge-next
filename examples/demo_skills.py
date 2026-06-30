import os
import sys
import json
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner, DEFAULT_SYSTEM_PROMPT
from forge.tools import registry
from forge.skills import SkillsManager

class SkillsMockModel(BaseModel):
    """A simulated model that attempts to call a dynamically loaded git skill. 
    First attempts with an invalid message format, receives a formatting error 
    from the skill script, reads the prompt guidelines, and self-corrects 
    with a valid Angular commit message.
    """
    
    def __init__(self):
        self.step_idx = 0

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1
        
        # Iteration 1: The model tries to commit but violates the Angular specification (Capitalized, period)
        if self.step_idx == 1:
            print("[MockModel] Thinking: Committing workspace updates. Writing message: 'Added skills bundle loader.'")
            return (
                "I will apply a git commit to save our local progress.",
                [{"id": "sk_call_1", "type": "function", "function": {
                    "name": "git_commit_raw",
                    "arguments": json.dumps({"message": "Added skills bundle loader."})
                }}]
            )
            
        # Iteration 2: After receiving the Lint error, it self-corrects to a lowercase, prefixed message
        elif self.step_idx == 2:
            print("[MockModel] Thinking: Ah, my commit message was rejected. According to GitCommitExpert guidelines in my system instructions, I must use feat: or fix: in lowercase without trailing period.")
            return (
                "My previous commit message was rejected. I will rewrite it to strictly conform to Angular git rules.",
                [{"id": "sk_call_2", "type": "function", "function": {
                    "name": "git_commit_raw",
                    "arguments": json.dumps({"message": "feat: implement local skills bundle library"})
                }}]
            )
        # Iteration 3: Done
        else:
            print("[MockModel] Thinking: Commit applied. Ending task.")
            return ("The git commit was successfully applied following Angular standards.\n\n[Polite Mode: Active] Thank you for pair programming with me!", None)


def main():
    # Setup Skills Manager pointing to the root 'skills/' folder
    skills_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../skills"))
    manager = SkillsManager(skills_dir=skills_dir)
    
    print("[Demo Setup] Loading custom skill bundles dynamically...")
    loaded_tools, prompt_extension = manager.load_skills(registry)
    print(f"[Demo Setup] Remote tools loaded: {loaded_tools}")
    
    # Bundle system prompts extension to give Agent the cognitive guideline rules
    extended_system_prompt = DEFAULT_SYSTEM_PROMPT + "\n\n" + prompt_extension
    
    task = "Commit the workspace changes using the git_commit_raw tool."
    
    # Initialize runner in sandbox
    workspace = os.path.abspath("temp_skills")
    if not os.path.exists(workspace):
        os.makedirs(workspace)
        
    try:
        model = SkillsMockModel()
        runner = AgentRunner(
            model=model, 
            system_prompt=extended_system_prompt,
            workspace_dir=workspace,
            test_command="python -c \"pass\""
        )
        
        trace = runner.run(task, max_iterations=4, checkpoint_path="skills_checkpoint.json")
        trace.print_summary()
        
    finally:
        # Clean up sandbox folder
        if os.path.exists("temp_skills"):
            import shutil
            shutil.rmtree("temp_skills")
            print("[Demo Cleanup] Removed temp_skills workspace.")

if __name__ == "__main__":
    main()

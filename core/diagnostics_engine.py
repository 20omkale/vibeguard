import os
from pathlib import Path

class DiagnosticsEngine:
    def __init__(self, project_path):
        self.project_path = Path(project_path)
    
    def run_scan(self):
        issues = []
        files_scanned = 0
        
        # 1. Tech Debt Scan (TODOs)
        # 2. Security Scan (Hardcoded keys, etc.)
        # 3. Structural Scan (Missing README, large files)
        
        try:
            for root, dirs, files in os.walk(self.project_path):
                if any(x in root for x in [".git", "node_modules", "__pycache__"]): continue
                
                for file in files:
                    if file.endswith((".py", ".js", ".html", ".css", ".md")):
                        files_scanned += 1
                        p = Path(root) / file
                        content = p.read_text(errors="ignore")
                        
                        # Check for TODOs
                        if "TODO" in content or "FIXME" in content:
                            issues.append(f"🚩 Technical Debt: Found pending tasks in {file}")
                        
                        # Check for common security risks
                        if "api_key" in content.lower() and "=" in content and "'" in content:
                            issues.append(f"⚠️ Security: Potential hardcoded API key in {file}")
                            
                        # File size check
                        if p.stat().st_size > 50000:
                            issues.append(f"📦 Performance: {file} is unusually large ({p.stat().st_size // 1024}KB)")

            if not issues:
                return f"✅ Clean Scan: {files_scanned} files analyzed. No critical flaws detected."
            
            return f"Found {len(issues)} architectural insights across {files_scanned} files:\n\n" + "\n".join(issues)
            
        except Exception as e:
            return f"❌ Scan Failed: {str(e)}"

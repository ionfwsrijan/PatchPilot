import os
import re
import json
import logging
import urllib.request
import tarfile
import tempfile
import ast

logger = logging.getLogger(__name__)

class DeltaAnalysisEngine:
    """
    Engine to handle Delta Analysis for auditing dependency version bumps (Issue #106).
    """
    def __init__(self, dependency_name: str = None, old_version: str = None, new_version: str = None):
        self.dependency_name = dependency_name
        self.old_version = old_version
        self.new_version = new_version
        
        # Placeholders for collected audit data
        self.added_files = []
        self.suspicious_patterns = []

    def parse_manifest_diff(self, diff_text: str) -> bool:
        """
        Step 1: Manifest Diffing.
        Parses a raw diff string line to extract package version changes.
        """
        try:
            pattern = r"([\w\-]+):\s*([\d\.]+)\s*->\s*([\d\.]+)"
            match = re.search(pattern, diff_text)
            
            if match:
                self.dependency_name = match.group(1)
                self.old_version = match.group(2)
                self.new_version = match.group(3)
                return True
            return False
        except Exception as e:
            logger.error(f"Error parsing manifest diff: {str(e)}")
            return False

    def fetch_upstream_package(self, version: str) -> str:
        """
        Step 2: Upstream Registry Fetching & Downloading.
        """
        if not self.dependency_name:
            return ""

        url = f"https://pypi.org/pypi/{self.dependency_name}/{version}/json"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status != 200:
                    return ""
                data = json.loads(response.read().decode())
                
            tarball_url = None
            for url_info in data.get("urls", []):
                if url_info.get("packagetype") == "sdist":
                    tarball_url = url_info.get("url")
                    break
            
            if not tarball_url:
                return ""

            temp_extract_dir = tempfile.mkdtemp(prefix=f"patchpilot_{self.dependency_name}_{version}_")
            archive_path = os.path.join(temp_extract_dir, f"package_{version}.tar.gz")

            urllib.request.urlretrieve(tarball_url, archive_path)

            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=temp_extract_dir)
                
            os.remove(archive_path)
            return temp_extract_dir

        except Exception as e:
            logger.error(f"Failed handling upstream fetching/extraction for v{version}: {str(e)}")
            return ""

    def audit_code_changes(self, old_dir: str, new_dir: str):
        """
        Step 3: Code Changes Audit.
        Compares directory structures to identify new files, and scans code signatures.
        """
        old_files = set()
        new_files_map = {}

        # Walk through the old version files to establish a baseline
        for root, _, files in os.walk(old_dir):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), old_dir)
                # Strip the top-level folder name inside the tarball to make paths clean
                clean_rel_path = "/".join(rel_path.split(os.sep)[1:])
                old_files.add(clean_rel_path)

        # Walk through the new version files to identify added files and inspect contents
        for root, _, files in os.walk(new_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, new_dir)
                clean_rel_path = "/".join(rel_path.split(os.sep)[1:])
                
                # Check if this file didn't exist in the old version
                if clean_rel_path and clean_rel_path not in old_files:
                    # Ignore metadata directories like egg-info or PKG-INFO
                    if not any(x in clean_rel_path for x in ["egg-info", "PKG-INFO", "setup.cfg"]):
                        self.added_files.append(clean_rel_path)
                
                # If it's a Python file, scan it for critical risks like eval()
                if file.endswith(".py"):
                    self._scan_file_ast(full_path, clean_rel_path)

    def _scan_file_ast(self, real_file_path: str, clean_display_path: str):
        """
        Runs an Abstract Syntax Tree (AST) scan looking for high-risk language primitives.
        """
        try:
            with open(real_file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            tree = ast.parse(content, filename=real_file_path)
            
            # Node walker to look for function calls named 'eval'
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "eval":
                        line_no = node.lineno
                        self.suspicious_patterns.append(
                            f"eval() usage in {clean_display_path}:{line_no}"
                        )
        except Exception as e:
            # If a single file fails parsing, log it but keep scanning other files safely
            logger.debug(f"Could not parse AST for {clean_display_path}: {str(e)}")

    def run_audit(self) -> dict:
        """
        Main execution flow for the delta audit pipeline.
        """
        if not all([self.dependency_name, self.old_version, self.new_version]):
            return {"error": "Missing dependency details. Ensure manifest diffing runs successfully first."}
            
        try:
            logger.info(f"Starting delta analysis for {self.dependency_name}: {self.old_version} -> {self.new_version}")
            
            old_dir = self.fetch_upstream_package(self.old_version)
            new_dir = self.fetch_upstream_package(self.new_version)
            
            if not old_dir or not new_dir:
                return {"error": "Failed to download and extract package versions from upstream registry."}
            
            # Execute step 3 audit logic
            self.audit_code_changes(old_dir, new_dir)
            
            return self.generate_output_payload()
            
        except Exception as e:
            logger.error(f"Error during delta analysis execution: {str(e)}")
            return {"error": f"Analysis failed: {str(e)}"}

    def generate_output_payload(self) -> dict:
        """
        Formats the final audited results into the expected output schema.
        """
        return {
            "supply_chain_diff": {
                "dependency": self.dependency_name,
                "upgrade_path": f"{self.old_version} -> {self.new_version}",
                "risk_assessment": {
                    "added_files": self.added_files,
                    "suspicious_patterns_detected": self.suspicious_patterns,
                    "overall_risk_score": self._calculate_risk_score()
                }
            }
        }

    def _calculate_risk_score(self) -> str:
        """
        Internal helper to evaluate overall risk level.
        """
        if self.suspicious_patterns:
            return "elevated"
        return "low"
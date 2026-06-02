"""
Test script: Verify rich metadata extraction from the enhanced AST parser.
Run: python scratch/test_rich_parser.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create a temporary Python file to test parsing
SAMPLE_PY = """
import os
from typing import Optional
from pathlib import Path


class UserService:
    \"\"\"Service for managing user accounts.\"\"\"

    def __init__(self, db_client):
        self.db = db_client

    async def get_user(self, user_id: int, include_deleted: bool = False) -> Optional[dict]:
        \"\"\"Fetch a user by ID from the database.

        Args:
            user_id: The primary key of the user.
            include_deleted: Whether to include soft-deleted users.

        Returns:
            User dict or None if not found.

        Raises:
            ValueError: If user_id is negative.
            ConnectionError: If DB is unavailable.
        \"\"\"
        if user_id < 0:
            raise ValueError("user_id must be positive")

        try:
            result = self.db.query("SELECT * FROM users WHERE id = ?", user_id)
            if not result and not include_deleted:
                return None
            return result
        except Exception as e:
            raise ConnectionError(f"DB error: {e}")

    def _validate_email(self, email: str) -> bool:
        \"\"\"Internal validation helper.\"\"\"
        if "@" not in email or "." not in email:
            return False
        return True

    @staticmethod
    def format_name(first: str, last: str) -> str:
        return f"{first} {last}"
"""

def main():
    # Write sample file
    test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_sample")
    os.makedirs(test_dir, exist_ok=True)
    test_file = os.path.join(test_dir, "sample.py")

    with open(test_file, "w", encoding="utf-8") as f:
        f.write(SAMPLE_PY)

    try:
        from parsers.ast_parser import parse_file
        result = parse_file(test_file)

        if not result:
            print("❌ FAIL: parse_file returned None")
            return

        print(f"✅ Parsed file: {result['file']}")
        print(f"   Language: {result['language']}")
        print(f"   Nodes found: {len(result['nodes'])}")
        print()

        for node in result["nodes"]:
            print(f"{'='*60}")
            print(f"  Name:        {node['name']}")
            print(f"  Type:        {node['type']}")
            print(f"  Lines:       {node['start_line']}-{node['end_line']}")
            print(f"  Async:       {node.get('is_async', '?')}")
            print(f"  Visibility:  {node.get('visibility', '?')}")
            print(f"  Class:       {node.get('class_name', '?')}")
            print(f"  Complexity:  {node.get('complexity', '?')}")
            print(f"  Return type: {node.get('output', '?')}")

            # Parse inputs JSON
            inputs_raw = node.get("inputs", "[]")
            try:
                inputs = json.loads(inputs_raw) if isinstance(inputs_raw, str) else inputs_raw
            except:
                inputs = inputs_raw
            print(f"  Inputs:      {json.dumps(inputs, indent=2)}")

            # Parse raises JSON
            raises_raw = node.get("raises", "[]")
            try:
                raises = json.loads(raises_raw) if isinstance(raises_raw, str) else raises_raw
            except:
                raises = raises_raw
            print(f"  Raises:      {raises}")

            # Parse annotations
            annotations_raw = node.get("annotations", "[]")
            try:
                annotations = json.loads(annotations_raw) if isinstance(annotations_raw, str) else annotations_raw
            except:
                annotations = annotations_raw
            print(f"  Decorators:  {annotations}")

            docstring = node.get("docstring", "")
            if docstring:
                print(f"  Docstring:   {docstring[:100]}...")

            print(f"  Calls:       {node.get('calls', [])}")
            print()

        # ── Validation checks ──
        print("=" * 60)
        print("VALIDATION CHECKS")
        print("=" * 60)

        node_names = {n["name"] for n in result["nodes"]}
        errors = []

        # Check that key functions were found
        for expected in ["UserService", "__init__", "get_user", "_validate_email", "format_name"]:
            if expected not in node_names:
                errors.append(f"Missing node: {expected}")

        # Check get_user properties
        get_user = next((n for n in result["nodes"] if n["name"] == "get_user"), None)
        if get_user:
            if not get_user.get("is_async"):
                errors.append("get_user should be async=True")
            if get_user.get("visibility") != "public":
                errors.append(f"get_user should be public, got {get_user.get('visibility')}")

            inputs = json.loads(get_user.get("inputs", "[]"))
            param_names = [p["name"] for p in inputs]
            if "user_id" not in param_names:
                errors.append("get_user missing param 'user_id'")
            if "include_deleted" not in param_names:
                errors.append("get_user missing param 'include_deleted'")

            raises = json.loads(get_user.get("raises", "[]"))
            if "ValueError" not in raises:
                errors.append(f"get_user should raise ValueError, got {raises}")
            if "ConnectionError" not in raises:
                errors.append(f"get_user should raise ConnectionError, got {raises}")

            if get_user.get("complexity", 0) < 3:
                errors.append(f"get_user complexity should be >=3, got {get_user.get('complexity')}")

        # Check _validate_email visibility
        validate = next((n for n in result["nodes"] if n["name"] == "_validate_email"), None)
        if validate:
            if validate.get("visibility") != "protected":
                errors.append(f"_validate_email should be protected, got {validate.get('visibility')}")

        if errors:
            print(f"\n❌ {len(errors)} validation errors:")
            for e in errors:
                print(f"   - {e}")
        else:
            print("\n✅ All validation checks passed!")

    finally:
        # Cleanup
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


if __name__ == "__main__":
    main()

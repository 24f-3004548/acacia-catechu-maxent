"""Execute and save the single Acacia catechu notebook with the project Python environment."""
import ast
import json
from pathlib import Path

import matplotlib
from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output

ROOT = Path(__file__).resolve().parents[1]
matplotlib.use("module://matplotlib_inline.backend_inline")
path = ROOT / "notebooks/acacia_catechu_india.ipynb"
notebook = json.loads(path.read_text())
shell = InteractiveShell.instance()
shell.user_ns["__file__"] = str(path)
import os
os.chdir(ROOT)
count = 0
for cell in notebook["cells"]:
    if cell["cell_type"] != "code":
        continue
    count += 1
    source = "".join(cell["source"])
    ast.parse(source)
    with capture_output() as captured:
        result = shell.run_cell(source, store_history=True)
    outputs = []
    if captured.stderr:
        outputs.append(dict(output_type="stream", name="stderr", text=captured.stderr))
    for display in captured.outputs:
        outputs.append(dict(output_type="display_data", data=display.data, metadata=display.metadata))
    error = result.error_before_exec or result.error_in_exec
    if error:
        outputs.append(dict(output_type="error", ename=type(error).__name__, evalue=str(error), traceback=[]))
    if result.result is not None:
        data, metadata = shell.display_formatter.format(result.result)
        outputs.append(dict(output_type="execute_result", data=data, metadata=metadata, execution_count=count))
    cell.update(outputs=outputs, execution_count=count)
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    if error:
        raise RuntimeError(f"Acacia notebook cell {count} failed") from error
    if count % 10 == 0:
        print(f"Completed {count} cells", flush=True)
print(json.dumps(shell.user_ns["summary_row"], indent=2))

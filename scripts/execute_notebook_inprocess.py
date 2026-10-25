"""Execute trusted project notebook cells with IPython without a socket server."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import os
import nbformat
from IPython.core.interactiveshell import InteractiveShell
from IPython.core.displayhook import CapturingDisplayHook
from IPython.utils.capture import capture_output

p=argparse.ArgumentParser()
p.add_argument('notebook',type=Path)
p.add_argument('--root',type=Path,required=True)
args=p.parse_args()
path=args.notebook.resolve()
os.chdir(args.root.resolve())
nb=nbformat.read(path,as_version=4)
shell=InteractiveShell.instance()
hook=CapturingDisplayHook(shell)
shell.display_trap.hook=hook
count=0
for cell in nb.cells:
    if cell.cell_type!='code':continue
    hook.outputs.clear()
    with capture_output() as captured:
        result=shell.run_cell(cell.source,store_history=True)
    error=result.error_before_exec or result.error_in_exec
    if error:raise RuntimeError(f'Notebook cell {count+1} failed') from error
    outputs=[]
    if captured.stdout:outputs.append(nbformat.v4.new_output('stream',name='stdout',text=captured.stdout))
    if captured.stderr:outputs.append(nbformat.v4.new_output('stream',name='stderr',text=captured.stderr))
    for item in captured.outputs:
        outputs.append(nbformat.v4.new_output('display_data',data=item.data,metadata=item.metadata))
    for item in hook.outputs:
        outputs.append(nbformat.v4.new_output('execute_result',data=item['data'],metadata=item['metadata'],execution_count=result.execution_count))
    cell.outputs=outputs
    cell.execution_count=result.execution_count
    count+=1
nb.metadata['execution']={'engine':'IPython InteractiveShell','transport':'in_process','executed_at':datetime.now(timezone.utc).isoformat(),'status':'all_cells_passed'}
nbformat.validate(nb)
nbformat.write(nb,path)
print({'executed_code_cells':count,'outputs':sum(len(c.get('outputs',[])) for c in nb.cells),'path':str(path)})

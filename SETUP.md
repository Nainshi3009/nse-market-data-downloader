# Windows setup

Run these commands from the project folder in the VS Code PowerShell terminal.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, allow scripts for this terminal only and then
activate the environment:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

The `(.venv)` prefix in the terminal indicates that the virtual environment is
active. To leave it, run `deactivate`.

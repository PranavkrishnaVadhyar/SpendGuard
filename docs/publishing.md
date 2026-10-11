# Publish spnd-guard

The distribution name is **spnd-guard**, version **0.1.0**. Python imports stay
`from spendguard import SpendGuard, Policy`; the console command stays
`spendguard`. The standalone `package_release/` directory is the upload source.
Publication has not yet been confirmed. Only Python 3.14 has been exercised
locally; the declared Python 3.10+ compatibility has not been matrix-tested.

## Build and validate

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install build twine
.\.venv\Scripts\python.exe -m build package_release
.\.venv\Scripts\python.exe -m twine check --strict package_release\dist\spnd_guard-0.1.0-py3-none-any.whl package_release\dist\spnd_guard-0.1.0.tar.gz
```

Before each release, keep runtime files in `spendguard/` and
`package_release/spendguard/` identical, update both versions, and run tests.
Inspect both archives for credentials, environment files, databases, caches,
and unrelated code. Keep `dist/` ignored. The repository has no chosen license;
no license or author identity has been invented in package metadata. Choose
and document a license before representing this as an open-source release.

## Upload

Create/sign in to your own [PyPI account](https://pypi.org/account/register/),
complete its account requirements, and create an API token. Never paste a token
into chat, source, `.env.example`, or a command that could be logged. Twine can
prompt for it without displaying it. Use `__token__` as the username and paste
the token at the hidden password prompt:

```powershell
.\.venv\Scripts\python.exe -m twine upload --username __token__ package_release\dist\spnd_guard-0.1.0-py3-none-any.whl package_release\dist\spnd_guard-0.1.0.tar.gz
```

For an initial project, a token may need account-wide scope; after creation,
prefer a project-scoped token. A token for TestPyPI cannot upload to PyPI.
To rehearse, use a separate [TestPyPI account](https://test.pypi.org/) and add
`--repository testpypi` to the upload command. Check the target carefully:
uploads are public and an uploaded filename/version cannot simply be replaced.
If the project name is unavailable or reserved, do not silently choose another.
The public JSON endpoint not finding a project does not guarantee availability.

## Verify and use after publication

Check [the project page](https://pypi.org/project/spnd-guard/), then install in
a fresh environment outside this repository so local source cannot mask errors:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "spnd-guard==0.1.0"
.\.venv\Scripts\python.exe -c "from spendguard import SpendGuard, Policy; from importlib.metadata import version; print(version('spnd-guard'))"
# Optional LangChain integration and dashboard:
.\.venv\Scripts\python.exe -m pip install "spnd-guard[langchain,dashboard]==0.1.0"
```

Install your model-provider integration separately. Existing databases and
configuration variables retain their `spendguard` names. Users with the previous
local `spendguard` distribution should use a fresh environment; both distributions
own the same import/CLI files and should not be installed side by side.

Workflow follows the official
[Python packaging guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/).

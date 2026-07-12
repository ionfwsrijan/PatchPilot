import pathlib

# Resolve the path to the actual backend app package
_backend_app = pathlib.Path(__file__).resolve().parent.parent / "backend" / "app"

# If the backend app directory exists, add it to this package's __path__
# so that imports like `app.main` resolve to the files under backend/app.
if _backend_app.is_dir():
    __path__.append(str(_backend_app))

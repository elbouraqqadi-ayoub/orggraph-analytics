"""Filesystem publication helper, independent of Spark for local regression tests."""


def publish_directory(fs, make_path, staging, destination, run_id):
    """Keep the previous output and restore it if the staged rename fails."""
    target, staged = make_path(destination), make_path(staging)
    previous = destination + "_previous_" + run_id
    moved = fs.exists(target)
    if moved and not fs.rename(target, make_path(previous)):
        raise OSError("Impossible de préserver la sortie Spark précédente.")
    try:
        if not fs.rename(staged, target):
            raise OSError("Impossible de publier la sortie Spark préparée.")
    except Exception:
        if moved and not fs.rename(make_path(previous), target):
            raise OSError(f"Restauration impossible. Sortie précédente conservée dans {previous}")
        raise
    return previous if moved else None

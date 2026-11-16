from . import import_check, prep, timing, validate

# name -> module with run(part_dir), INPUTS, OUTPUTS
STAGES = {"prep": prep, "import_check": import_check, "timing": timing, "validate": validate}

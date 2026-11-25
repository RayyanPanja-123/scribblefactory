from . import audio, finish, import_check, prep, render, shots, timing, tts, validate

# name -> module with run(part_dir), INPUTS, OUTPUTS
STAGES = {"prep": prep, "tts": tts, "import_check": import_check, "timing": timing,
          "shots": shots, "validate": validate, "render": render,
          "audio": audio, "finish": finish}

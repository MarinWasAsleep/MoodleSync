import os
import sys

d = sys.argv[1] if len(sys.argv) > 1 else "/opt/data/cache/scratch/faux-moteur"
os.makedirs(d, exist_ok=True)
p = os.path.join(d, "tesseract")
corps = (
    "#!/bin/sh\n"
    'if [ "$1" = "--version" ]; then\n'
    '  printf "tesseract 5.5.3\\n leptonica-1.84.1\\n"\n'
    "  exit 0\n"
    "fi\n"
    "exit 0\n"
)
with open(p, "w", newline="\n") as f:
    f.write(corps)
os.chmod(p, 0o755)
print(p, oct(os.stat(p).st_mode))

"""Initialize the mounted volume, then irrevocably drop privileges before polling."""
import os
from pathlib import Path


def main():
    if os.geteuid() == 0:
        # Fixed deployment mount only; never recurse over user-supplied paths.
        Path('/data').mkdir(exist_ok=True)
        os.chown('/data', 10001, 10001)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
        os.environ['HOME'] = '/home/decoder'
    from .service import run
    run()


if __name__ == '__main__':
    main()

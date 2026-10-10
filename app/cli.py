import sys
from .db import migrate
if __name__=='__main__':
    if sys.argv[1:]!=['migrate']:raise SystemExit('usage: python -m app.cli migrate')
    migrate();print('Schema ready')

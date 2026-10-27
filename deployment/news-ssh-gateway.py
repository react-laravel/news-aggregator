#!/usr/bin/python3 -I
import os
import re
import sys

COMMAND = re.compile(r'(receive|publish|validate) ([0-9a-f]{40})\Z')

def parse_command(value):
    match = COMMAND.fullmatch(value)
    if not match:
        raise ValueError('Only News receive/publish/validate is allowed')
    return match.groups()

def main():
    command, revision = parse_command(os.environ.get('SSH_ORIGINAL_COMMAND', ''))
    path = '/usr/local/libexec/publish-news'
    os.execv(path, [path, command, revision])

if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)

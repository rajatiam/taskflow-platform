"""Explicit administration; passwords never appear in command arguments."""
import argparse, getpass, re
from backend import security
import app as store

parser=argparse.ArgumentParser()
parser.add_argument('command',choices=['create-admin','migrate'])
parser.add_argument('--username')
args=parser.parse_args()
if args.command=='migrate':
    store.connect().close(); print('Database migrations applied.')
else:
    username=args.username or input('Administrator username: ')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',username): parser.error('Use 3–40 letters, digits, underscore, period, or hyphen')
    password=getpass.getpass('Password (12–128 characters): ')
    if not 12<=len(password)<=128: parser.error('Password length must be 12–128 characters')
    if password!=getpass.getpass('Confirm password: '): parser.error('Passwords differ')
    security.register(store.DB,username,password,role='admin')
    print('Administrator created. Sign in through the application.')

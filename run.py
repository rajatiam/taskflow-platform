"""Start the backend and built Angular frontend on this project's port."""
import os
import uvicorn
from app import CONFIG

if __name__ == '__main__':
    uvicorn.run('api:app', host=os.environ.get('HOST','127.0.0.1'), port=int(os.environ.get('PORT',CONFIG['port'])))

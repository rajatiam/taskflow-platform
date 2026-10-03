import logging
import uvicorn
from backend.configuration import settings
from app import CONFIG

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    config=settings(CONFIG)
    uvicorn.run('backend.api:app',host=config.host,port=config.port)

import logging.config

from gunicorn import glogging

logging_cfg = {
		'version': 1,
		'disable_existing_loggers': False,
		'formatters': {
			'KeyValueFormatter': {
				'format': (
					'%(asctime)s '
					'[%(levelname)s] message=%(message)s'
				)
			},
		},
		'handlers': {
			'console': {
				'level': 'INFO',
				'class': 'logging.StreamHandler',
				'formatter': 'KeyValueFormatter',
			},
            'gunicorn_access_file': {
				'level': 'INFO',
				'class': 'logging.FileHandler',
				'filename': 'log/gunicorn_access.log',
				'formatter': 'KeyValueFormatter',
			},
            'gunicorn_error_file': {
				'level': 'INFO',
				'class': 'logging.FileHandler',
				'filename': 'log/gunicorn_error.log',
				'formatter': 'KeyValueFormatter',
			},
		},
		'loggers': {
			'gunicorn.error': {
				'handlers': ['gunicorn_error_file', 'console'],
				'level': 'INFO',
				'propagate': False,
			},
            'gunicorn.access': {
				'handlers': ['gunicorn_access_file','console'],
				'level': 'INFO',
				'propagate': False,
			},
    	},
        'root': {
			'level': 'INFO',
			'handlers': ['console'],
		}
}


logger = logging.getLogger(__name__)

def get_result():
    logger.info('Calculating result')
    return b'Hello world!'

def wsgi_app(environ, start_response):
    result = get_result()
    start_response('200 OK', [('Content-Type', 'text/html')])
    return [result]

def configure_logging():
    logging.config.dictConfig(logging_cfg)

class UniformLogger(glogging.Logger):

    def setup(self, cfg):
        configure_logging()


if __name__ == '__main__':
    configure_logging()
    print(get_result())
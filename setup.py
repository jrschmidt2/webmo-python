from distutils.core import setup
setup(
  name = 'webmo',
  packages = ['webmo'],
  version = '1.1.0',
  license='MIT',
  description = 'A Python-based interface to WebMO',
  author = 'J.R. Schmidt',
  author_email = 'schmidt@webmo.net',
  url = 'https://github.com/jrschmidt2/webmo-python',
  download_url = 'https://github.com/jrschmidt2/webmo-python/archive/refs/tags/1.1.0.tar.gz',
  keywords = ['WEBMO', 'REST', 'API'],
  install_requires=[
          'requests',
          'websockets',
      ],
)

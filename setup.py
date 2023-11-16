from distutils.core import setup
import codecs
import os.path

def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()

def get_version(rel_path):
    for line in read(rel_path).splitlines():
        if line.startswith('__version__'):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    else:
        raise RuntimeError("Unable to find version string.")

version = get_version("webmo/__init__.py")

setup(
  name = 'webmo',
  packages = ['webmo'],
  version = version,
  license='MIT',
  description = 'A Python-based interface to WebMO',
  author = 'J.R. Schmidt',
  author_email = 'schmidt@webmo.net',
  url = 'https://github.com/jrschmidt2/webmo-python',
  download_url = 'https://github.com/jrschmidt2/webmo-python/archive/refs/tags/%s.tar.gz' % version,
  keywords = ['WEBMO', 'REST', 'API'],
  install_requires=[
          'requests',
          'websockets',
      ],
)
